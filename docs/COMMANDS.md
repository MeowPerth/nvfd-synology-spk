# 群晖 RTX 2080 Ti 风扇与频率控制报告

> 2026-10-24 更新：已经打包成 DSM 套件 `NVFD-1.0.0-0016.spk`，可在套件中心
> 安装后用鼠标操作。安装和使用见 [README.md](../README.md)。下面保留
> 命令行/原理说明，手工命令仍然可用。

日期：2026-10-24
主机：测试用群晖（DSM 7.4.0-90075，内核 5.10.55+，x86_64）
显卡：2 × NVIDIA GeForce RTX 2080 Ti
驱动：615.78.08（已由你移植并可正常使用）

## 结论

1. **风扇可以控制**：已把 [NVFD](https://github.com/infinirc/nvfd) 移植/编译到 DSM，使用 NVIDIA 驱动自带的 `libnvidia-ml.so.1`（NVML），不依赖 `nvidia-settings`、X11 或 CUDA Toolkit。
2. **核心频率可以调**：`nvidia-smi -lgc` 锁定核心频率可用（实测锁 800 MHz 后实际约 810 MHz，随后已恢复自动）。
3. **显存频率可以调，但不能用“锁定”方式**：GeForce 上 `nvidia-smi -lmc` 返回 `not supported`；改用 NVML 的显存 VF 偏移接口，实测 -100 MHz 后显存从 6800 MHz 降到 6750 MHz，随后已恢复 0。
4. **功率上限可以调**：两张卡当前限制分别为 230 W / 215 W，可调范围 100–320 W。
5. 群晖已安装并启用 `nvfd.service`，开机自动接管风扇；当前使用 NVFD 默认风扇曲线（65 °C 左右约 73–75%）。

## 已安装内容

| 路径 | 作用 |
|---|---|
| `/usr/local/bin/nvfd` | NVFD 主程序（风扇曲线/手动/自动） |
| `/usr/local/bin/nvfd-clocks` | 核心/显存 VF 偏移工具（Python + NVML） |
| `/etc/systemd/system/nvfd.service` | 开机启动、等待驱动、看门狗、退出时恢复自动风扇 |
| `/usr/local/nvfd/README.md` | 本报告的副本 |
| `/etc/nvfd/config.json` | 每张卡的风扇模式（当前两张都是 `curve`） |
| `/etc/nvfd/curve.json` | 风扇曲线 |
| `/etc/nvfd/clocks.json` | 已保存的核心/显存偏移（当前都是 0） |

## 常用风扇命令

```bash
sudo nvfd status                 # 查看模式、温度、每个风扇转速
sudo nvfd list                   # 查看 GPU 编号
sudo nvfd 0 60                   # GPU 0 固定 60%
sudo nvfd 0 curve                # GPU 0 使用曲线
sudo nvfd 0 auto                 # GPU 0 交回驱动自动控制
sudo nvfd auto                   # 所有 GPU 交回驱动
sudo nvfd curve 70 80            # 修改曲线：70 °C 对应 80%
sudo nvfd curve show             # 查看曲线
```

NVFD 守护进程每 5 秒重读配置，所以上面的模式/曲线修改会在 5 秒内生效，不需要重启服务。

当前曲线：

```json
{
  "30": 30,
  "40": 40,
  "50": 55,
  "60": 65,
  "70": 85,
  "80": 100
}
```

如果觉得 65 °C 时 75% 太吵，可以把曲线改缓，例如：

```bash
sudo nvfd curve 50 40
sudo nvfd curve 60 45
sudo nvfd curve 70 55
sudo nvfd curve 80 80
```

注意：曲线必须随温度单调不下降，否则 NVFD 会拒绝保存。

## 核心/显存频率命令

```bash
sudo nvfd-clocks status                  # 温度、频率、偏移、功率、风扇
sudo nvfd-clocks set all -50 0           # 核心 -50 MHz，显存不变
sudo nvfd-clocks set 0 100 200           # GPU 0：核心 +100，显存 +200
sudo nvfd-clocks reset                   # 全部恢复 0
```

偏移会写入 `/etc/nvfd/clocks.json`，`nvfd.service` 每次启动时通过
`ExecStartPre=/usr/local/bin/nvfd-clocks apply` 自动重新应用，因此可跨重启保留。

可调范围（由驱动报告）：

- 核心 GPC 偏移：`-1000 … +1000 MHz`
- 显存 MEM 偏移：`-2000 … +6000 MT/s`（命令行单位；网页界面按实际 MHz 显示为 `-1000 … +3000 MHz`）

正偏移属于超频，可能让正在跑的计算任务出错或让驱动不稳定。建议一次加 25–50 MHz，观察温度和任务是否正常后再继续。

### 锁定核心频率（另一种方式）

```bash
sudo nvidia-smi -i 0 -lgc 1500,1500      # 锁定 GPU 0 核心 1500 MHz
sudo nvidia-smi -i 0 -rgc                # 恢复自动
sudo nvidia-smi -i 1 -lgc 1500,1500
sudo nvidia-smi -i 1 -rgc
```

这种锁定在重启后失效；它和 `nvfd-clocks` 的 VF 偏移是两套机制，建议不要同时使用。

### 功耗上限

```bash
nvidia-smi -q -d POWER | grep -E "Power Limit|Min Power|Max Power"
sudo nvidia-smi -i 0 -pl 200
sudo nvidia-smi -i 0 -pl 230             # GPU 0 当前值
sudo nvidia-smi -i 1 -pl 200
sudo nvidia-smi -i 1 -pl 215             # GPU 1 当前值
```

降低功耗上限会直接降低频率和温度，适合长期跑满负载时使用。

## 重要观察：部分风扇通道回读为 0

当前 NVFD 下发的目标转速和实际回读：

| GPU | 风扇 | 目标 | 实际 |
|---|---|---|---|
| 0 | Fan 0 | 73% | 73% |
| 0 | Fan 1 | 73% | 0% |
| 1 | Fan 0 | 77% | 0% |
| 1 | Fan 1 | 77% | 0% |

也就是说：**只有 GPU 0 的 Fan 0 有实际转速回读**。GPU 0 的第二个风扇和 GPU 1 的两个风扇，驱动已经下发目标值，但转速一直为 0。把风扇强制到 100% 后，GPU 1 的温度也没有明显下降。

可能原因：

- 显卡改了水冷/风冷散热器，原厂风扇没接；
- 风扇供电或测速线没插好；
- 风扇本身损坏；
- 风扇通过主板/外置控制器供电，不经过显卡。

目前两张卡在 100% 负载下温度为 64–67 °C，没有过热迹象；机箱 4 个风扇也在转（约 1146/2749/2307/1893 RPM），所以暂时是安全的。但建议你现场确认 GPU 1 的风扇/散热器状态，特别是如果它原本应该是风冷卡。

## 服务与排错

```bash
sudo systemctl status nvfd
sudo journalctl -u nvfd -n 50 --no-pager
sudo systemctl restart nvfd
```

停止服务时 NVFD 会把风扇交回驱动自动控制；`ExecStopPost` 还会再执行一次
`nvfd reset-fans`，防止异常退出后风扇卡在固定转速。

## 回滚

```bash
sudo systemctl disable --now nvfd
sudo rm -f /usr/local/bin/nvfd /usr/local/bin/nvfd-clocks
sudo rm -f /etc/systemd/system/nvfd.service
sudo systemctl daemon-reload
# 配置保留在 /etc/nvfd，如不需要可自行删除
```

## 说明

- 全程没有关机、重启或卸载驱动。
- 没有修改群晖其他服务、共享目录或你的计算任务文件。
- 只新增了上面列出的文件。
- 由于不能重启验证，开机自启是按 systemd 的 `enable` 配置好的；服务本身已做过 stop/start/restart 测试。
- 单元里增加了最多 120 秒的 `/dev/nvidiactl` 等待，避免 DSM 启动时 NVIDIA 驱动还没加载完导致 NVFD 放弃启动。
