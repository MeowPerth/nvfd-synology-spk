// DSM 原生应用窗口注册。
// INFO.dsmappname 指向 AppInstance，ui/config 以本文件名为节键。
Ext.ns('MeowPerth.NVFDControl');

Ext.define('MeowPerth.NVFDControl.AppInstance', {
    extend: 'SYNO.SDS.AppInstance',
    appWindowName: 'MeowPerth.NVFDControl.AppWindow',
    constructor: function () {
        this.callParent(arguments);
    }
});

Ext.define('MeowPerth.NVFDControl.AppWindow', {
    extend: 'SYNO.SDS.AppWindow',
    constructor: function (config) {
        var cfg = Ext.apply({
            resizable: true,
            maximizable: true,
            minimizable: true,
            width: 1120,
            height: 820,
            minWidth: 720,
            minHeight: 520,
            layout: 'fit',
            border: false,
            cls: 'syno-app-nvfdcontrol-wrapper',
            items: [{
                xtype: 'box',
                autoEl: {
                    tag: 'iframe',
                    src: '/webman/3rdparty/NVFDControl/index.html?v=1.0.0-0019',
                    frameborder: '0',
                    style: 'width:100%; height:100%; border:none; background:#f2f4f7;'
                }
            }]
        }, config);
        this.callParent([cfg]);
    },
    onOpen: function (info) { this.callParent([info]); },
    onRequest: function (info) { this.onOpen(info); }
});
