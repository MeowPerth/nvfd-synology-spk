#!/usr/bin/env python3
"""NVFD package backend.

Runs as root through the DSM package's spm-exec wrapper.  It is intentionally
small and dependency-free: NVML via ctypes, JSON via the standard library.
"""

import ctypes
import json
import os
import shutil
import subprocess
import sys
from urllib.parse import parse_qs

CONFIG_DIR = "/etc/nvfd"
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
CURVE_FILE = os.path.join(CONFIG_DIR, "curve.json")
CLOCKS_FILE = os.path.join(CONFIG_DIR, "clocks.json")
PKG_DIR = os.environ.get("NVFD_PKG_DIR", "/var/packages/NVFDControl/target")
NVFD_BIN = os.path.join(PKG_DIR, "bin", "nvfd")
CLOCKS_BIN = os.path.join(PKG_DIR, "bin", "nvfd-clocks")
NVIDIA_SMI = "/usr/bin/nvidia-smi"

NVML_SUCCESS = 0
NVML_CLOCK_SM = 1
NVML_CLOCK_MEM = 2
DEFAULT_CURVE = {"30": 30, "40": 40, "50": 55, "60": 65, "70": 85, "80": 100}

ENV = dict(os.environ)
ENV["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ENV.setdefault("LC_ALL", "C")


def read_json(path, default):
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else default
    except Exception:
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=4, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)
    os.chmod(path, 0o644)


def run(cmd, timeout=25):
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, env=ENV, timeout=timeout)
        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()
        msg = "\n".join(x for x in (out, err) if x)
        return p.returncode, msg
    except Exception as e:
        return 1, str(e)


def service_state():
    systemctl = shutil.which("systemctl") or "/bin/systemctl"
    rc, out = run([systemctl, "is-active", "nvfd"], timeout=5)
    return out.strip() if out else "unknown"


class NVML:
    def __init__(self):
        L = ctypes.CDLL("libnvidia-ml.so.1")
        self.L = L
        L.nvmlInit_v2.restype = ctypes.c_int
        L.nvmlShutdown.restype = ctypes.c_int
        L.nvmlErrorString.restype = ctypes.c_char_p
        L.nvmlErrorString.argtypes = [ctypes.c_int]
        L.nvmlDeviceGetCount_v2.argtypes = [ctypes.POINTER(ctypes.c_uint)]
        L.nvmlDeviceGetHandleByIndex_v2.argtypes = [
            ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)]
        L.nvmlDeviceGetName.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint]
        L.nvmlDeviceGetTemperature.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint)]
        L.nvmlDeviceGetPowerUsage.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
        L.nvmlDeviceGetEnforcedPowerLimit.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
        L.nvmlDeviceGetPowerManagementLimitConstraints.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint)]
        L.nvmlDeviceGetPowerManagementDefaultLimit.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
        L.nvmlDeviceGetClockInfo.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint)]
        L.nvmlDeviceGetNumFans.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
        L.nvmlDeviceGetFanSpeed_v2.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint)]
        L.nvmlDeviceGetTargetFanSpeed.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint)]
        L.nvmlDeviceGetMinMaxFanSpeed.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint)]
        for name in ("nvmlDeviceGetGpcClkVfOffset",
                     "nvmlDeviceGetMemClkVfOffset"):
            fn = getattr(L, name)
            fn.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
            fn.restype = ctypes.c_int
        for name in ("nvmlDeviceSetGpcClkVfOffset",
                     "nvmlDeviceSetMemClkVfOffset"):
            fn = getattr(L, name)
            fn.argtypes = [ctypes.c_void_p, ctypes.c_int]
            fn.restype = ctypes.c_int
        for name in ("nvmlDeviceGetGpcClkMinMaxVfOffset",
                     "nvmlDeviceGetMemClkMinMaxVfOffset"):
            fn = getattr(L, name)
            fn.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
                           ctypes.POINTER(ctypes.c_int)]
            fn.restype = ctypes.c_int
        r = L.nvmlInit_v2()
        if r != NVML_SUCCESS:
            raise RuntimeError("NVML init failed: %s" % self.err(r))
        n = ctypes.c_uint()
        r = L.nvmlDeviceGetCount_v2(ctypes.byref(n))
        if r != NVML_SUCCESS:
            raise RuntimeError("NVML device count failed: %s" % self.err(r))
        self.count = n.value

    def err(self, r):
        return self.L.nvmlErrorString(r).decode("utf-8", "replace")

    def handle(self, index):
        d = ctypes.c_void_p()
        r = self.L.nvmlDeviceGetHandleByIndex_v2(index, ctypes.byref(d))
        if r != NVML_SUCCESS:
            raise RuntimeError("GPU %d handle failed: %s" % (index, self.err(r)))
        return d

    def name(self, d):
        buf = ctypes.create_string_buffer(96)
        r = self.L.nvmlDeviceGetName(d, buf, 96)
        return buf.value.decode("utf-8", "replace") if r == NVML_SUCCESS else "Unknown"

    def u(self, fn, d, *extra):
        v = ctypes.c_uint()
        r = fn(d, *(extra + (ctypes.byref(v),)))
        return v.value if r == NVML_SUCCESS else None

    def power_limits(self, d):
        lo = ctypes.c_uint()
        hi = ctypes.c_uint()
        r = self.L.nvmlDeviceGetPowerManagementLimitConstraints(
            d, ctypes.byref(lo), ctypes.byref(hi))
        if r != NVML_SUCCESS:
            return None, None
        return lo.value, hi.value

    def default_power(self, d):
        v = ctypes.c_uint()
        r = self.L.nvmlDeviceGetPowerManagementDefaultLimit(
            d, ctypes.byref(v))
        return v.value if r == NVML_SUCCESS else None

    def clock(self, d, kind):
        v = ctypes.c_uint()
        r = self.L.nvmlDeviceGetClockInfo(d, kind, ctypes.byref(v))
        return v.value if r == NVML_SUCCESS else None

    def fans(self, d):
        n = ctypes.c_uint()
        r = self.L.nvmlDeviceGetNumFans(d, ctypes.byref(n))
        if r != NVML_SUCCESS:
            return [], []
        actual, target = [], []
        for i in range(n.value):
            a = ctypes.c_uint()
            t = ctypes.c_uint()
            ra = self.L.nvmlDeviceGetFanSpeed_v2(d, i, ctypes.byref(a))
            rt = self.L.nvmlDeviceGetTargetFanSpeed(d, i, ctypes.byref(t))
            actual.append(a.value if ra == NVML_SUCCESS else None)
            target.append(t.value if rt == NVML_SUCCESS else None)
        return actual, target

    def fan_range(self, d):
        lo = ctypes.c_uint()
        hi = ctypes.c_uint()
        r = self.L.nvmlDeviceGetMinMaxFanSpeed(d, ctypes.byref(lo), ctypes.byref(hi))
        if r != NVML_SUCCESS:
            return None, None
        return lo.value, hi.value

    def offset(self, d, kind):
        v = ctypes.c_int()
        r = getattr(self.L, "nvmlDeviceGet%sClkVfOffset" % kind)(
            d, ctypes.byref(v))
        return v.value if r == NVML_SUCCESS else None

    def offset_range(self, d, kind):
        lo = ctypes.c_int()
        hi = ctypes.c_int()
        r = getattr(self.L, "nvmlDeviceGet%sClkMinMaxVfOffset" % kind)(
            d, ctypes.byref(lo), ctypes.byref(hi))
        return (lo.value, hi.value) if r == NVML_SUCCESS else (None, None)

    def shutdown(self):
        self.L.nvmlShutdown()


def status(nv):
    cfg = read_json(CONFIG_FILE, {})
    curve = read_json(CURVE_FILE, DEFAULT_CURVE)
    clocks = read_json(CLOCKS_FILE, {})
    gpus = []
    for i in range(nv.count):
        d = nv.handle(i)
        actual, target = nv.fans(d)
        fmin, fmax = nv.fan_range(d)
        pmin, pmax = nv.power_limits(d)
        entry = cfg.get("gpu%d" % i, {})
        if not isinstance(entry, dict):
            entry = {}
        centry = clocks.get("gpu%d" % i, {})
        if not isinstance(centry, dict):
            centry = {}
        gpc_off = nv.offset(d, "Gpc")
        mem_off = nv.offset(d, "Mem")
        gpc_range = nv.offset_range(d, "Gpc")
        mem_range = nv.offset_range(d, "Mem")
        gpus.append({
            "index": i,
            "name": nv.name(d),
            "temp": nv.u(nv.L.nvmlDeviceGetTemperature, d, ctypes.c_uint(0)),
            "power": nv.u(nv.L.nvmlDeviceGetPowerUsage, d),
            "power_limit": nv.u(nv.L.nvmlDeviceGetEnforcedPowerLimit, d),
            "power_default": nv.default_power(d),
            "power_min": pmin,
            "power_max": pmax,
            "sm_clock": nv.clock(d, NVML_CLOCK_SM),
            "mem_clock": nv.clock(d, NVML_CLOCK_MEM),
            "fans": actual,
            "fan_targets": target,
            "fan_min": fmin,
            "fan_max": fmax,
            "gpc_offset": gpc_off,
            "mem_offset": mem_off,
            "mem_offset_mhz": None if mem_off is None else int(round(mem_off / 2.0)),
            "gpc_saved": centry.get("gpc", 0),
            "mem_saved": centry.get("mem", 0),
            "gpc_range": gpc_range,
            "mem_range": mem_range,
            "mem_range_mhz": [None, None] if mem_range[0] is None else
                             [int(round(mem_range[0] / 2.0)), int(round(mem_range[1] / 2.0))],
            "mode": entry.get("mode", "auto"),
            "manual_speed": entry.get("speed"),
        })
    return {
        "ok": True,
        "service": service_state(),
        "gpus": gpus,
        "curve": curve,
        "config": cfg,
    }


def require_target(nv, target):
    if target == "all":
        return list(range(nv.count))
    try:
        i = int(target)
    except (TypeError, ValueError):
        raise RuntimeError("GPU 参数必须是 0、1 或 all")
    if i < 0 or i >= nv.count:
        raise RuntimeError("GPU %d 不存在" % i)
    return [i]


def set_mode(nv, target, mode, speed):
    if mode not in ("auto", "curve", "manual"):
        raise RuntimeError("未知风扇模式")
    indexes = require_target(nv, target)
    if mode == "manual":
        try:
            speed = int(speed)
        except (TypeError, ValueError):
            raise RuntimeError("手动转速必须是 30-100 的整数")
        if speed < 30 or speed > 100:
            raise RuntimeError("手动转速必须在 30-100 之间")
    cmds = []
    if target == "all":
        if mode == "auto":
            cmds.append([NVFD_BIN, "auto"])
        elif mode == "curve":
            cmds.append([NVFD_BIN, "curve"])
        else:
            cmds.append([NVFD_BIN, str(speed)])
    else:
        i = indexes[0]
        if mode == "auto":
            cmds.append([NVFD_BIN, str(i), "auto"])
        elif mode == "curve":
            cmds.append([NVFD_BIN, str(i), "curve"])
        else:
            cmds.append([NVFD_BIN, str(i), "manual", str(speed)])
    if not os.path.exists(NVFD_BIN):
        raise RuntimeError("找不到 NVFD 主程序: %s" % NVFD_BIN)
    messages = []
    for cmd in cmds:
        rc, msg = run(cmd)
        if rc != 0:
            raise RuntimeError(msg or "NVFD 命令失败")
        messages.append(msg)
    return {"ok": True, "message": "\n".join(x for x in messages if x) or "已应用"}


def set_curve(points_text):
    if not points_text:
        raise RuntimeError("曲线不能为空")
    pairs = []
    for item in points_text.replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise RuntimeError("曲线格式应为 温度:转速")
        t, s = item.split(":", 1)
        try:
            t = int(t)
            s = int(s)
        except ValueError:
            raise RuntimeError("曲线温度和转速必须是整数")
        if t < 0 or t > 100 or s < 0 or s > 100:
            raise RuntimeError("曲线温度和转速必须在 0-100 之间")
        pairs.append((t, s))
    if len(pairs) < 2:
        raise RuntimeError("至少需要两个曲线点")
    if len(pairs) > 16:
        raise RuntimeError("最多支持 16 个曲线点")
    pairs.sort()
    for a, b in zip(pairs, pairs[1:]):
        if a[0] == b[0]:
            raise RuntimeError("不能有两个相同温度的点")
        if b[1] < a[1]:
            raise RuntimeError("风扇转速必须随温度升高而不下降")
    curve = {str(t): s for t, s in pairs}
    write_json(CURVE_FILE, curve)
    return {"ok": True, "curve": curve, "message": "曲线已保存，约 5 秒内生效"}


def set_offsets(nv, target, gpc, mem, mem_mhz=None):
    indexes = require_target(nv, target)
    try:
        gpc = int(gpc)
        if mem_mhz is not None:
            mem = int(mem_mhz) * 2
        else:
            mem = int(mem)
    except (TypeError, ValueError):
        raise RuntimeError("偏移必须是整数")
    for i in indexes:
        d = nv.handle(i)
        gr = nv.offset_range(d, "Gpc")
        mr = nv.offset_range(d, "Mem")
        if gr[0] is not None and not (gr[0] <= gpc <= gr[1]):
            raise RuntimeError("GPU %d 核心偏移超出范围 %d..%d MHz" % (i, gr[0], gr[1]))
        if mr[0] is not None and not (mr[0] <= mem <= mr[1]):
            if mem_mhz is not None:
                raise RuntimeError("GPU %d 显存偏移超出范围 %d..%d MHz" %
                                   (i, int(round(mr[0] / 2.0)), int(round(mr[1] / 2.0))))
            raise RuntimeError("GPU %d 显存偏移超出范围 %d..%d MT/s" % (i, mr[0], mr[1]))
    if not os.path.exists(CLOCKS_BIN):
        raise RuntimeError("找不到 nvfd-clocks: %s" % CLOCKS_BIN)
    rc, msg = run([CLOCKS_BIN, "set", target, str(gpc), str(mem)])
    if rc != 0:
        raise RuntimeError(msg or "偏移设置失败")
    return {"ok": True, "message": msg or "偏移已应用"}


def reset_offsets(target):
    if not os.path.exists(CLOCKS_BIN):
        raise RuntimeError("找不到 nvfd-clocks: %s" % CLOCKS_BIN)
    cmd = [CLOCKS_BIN, "reset"]
    if target and target != "all":
        cmd.append(target)
    rc, msg = run(cmd)
    if rc != 0:
        raise RuntimeError(msg or "偏移归零失败")
    return {"ok": True, "message": msg or "偏移已归零"}


def set_power(nv, target, watts):
    indexes = require_target(nv, target)
    try:
        watts = int(watts)
    except (TypeError, ValueError):
        raise RuntimeError("功耗必须是整数瓦")
    for i in indexes:
        d = nv.handle(i)
        lo, hi = nv.power_limits(d)
        if lo is not None and hi is not None:
            if not (lo // 1000 <= watts <= (hi + 999) // 1000):
                raise RuntimeError("GPU %d 功耗范围 %.0f-%.0f W" %
                                   (i, lo / 1000.0, hi / 1000.0))
    messages = []
    for i in indexes:
        if not os.path.exists(NVIDIA_SMI):
            raise RuntimeError("找不到 nvidia-smi")
        rc, msg = run([NVIDIA_SMI, "-i", str(i), "-pl", str(watts)])
        if rc != 0:
            raise RuntimeError(msg or "功耗设置失败")
        messages.append(msg)
    return {"ok": True, "message": "\n".join(x for x in messages if x) or "功耗已设置",
            "note": "功耗上限重启后会恢复默认"}


def restart_service():
    systemctl = shutil.which("systemctl") or "/bin/systemctl"
    rc, msg = run([systemctl, "restart", "nvfd"], timeout=40)
    if rc != 0:
        raise RuntimeError(msg or "服务重启失败")
    return {"ok": True, "message": "NVFD 服务已重启"}


def handle_query(qs):
    q = parse_qs(qs, keep_blank_values=True)
    def one(key, default=None):
        v = q.get(key)
        return v[0] if v else default
    action = one("action", "status")
    nv = None
    try:
        nv = NVML()
        if action == "status":
            result = status(nv)
        elif action == "setmode":
            result = set_mode(nv, one("target", "all"), one("mode", "auto"), one("speed", "60"))
        elif action == "setcurve":
            result = set_curve(one("points", ""))
        elif action == "setoffsets":
            result = set_offsets(nv, one("target", "all"), one("gpc", "0"),
                                 one("mem", "0"), one("mem_mhz"))
        elif action == "resetoffsets":
            result = reset_offsets(one("target", "all"))
        elif action == "setpower":
            result = set_power(nv, one("target", "all"), one("watts", "200"))
        elif action == "restart":
            result = restart_service()
        else:
            raise RuntimeError("未知操作: %s" % action)
    except Exception as e:
        result = {"ok": False, "error": str(e)}
    finally:
        if nv is not None:
            try:
                nv.shutdown()
            except Exception:
                pass
    return result


def main():
    qs = sys.argv[1] if len(sys.argv) > 1 else ""
    print(json.dumps(handle_query(qs), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
