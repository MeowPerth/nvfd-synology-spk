Ext.define('SYNO.SDS.NVFD.Instance', {
    extend: 'SYNO.SDS.AppInstance',
    appWindowName: 'SYNO.SDS.NVFD.Main',
    constructor: function() {
        this.callParent(arguments);
    }
});

Ext.define('SYNO.SDS.NVFD.Main', {
    extend: 'SYNO.SDS.AppWindow',
    appInstance: null,

    constructor: function(cfg) {
        this.appInstance = cfg.appInstance;

        var config = Ext.apply({
            resizable: true,
            maximizable: true,
            minimizable: true,
            width: 1120,
            height: 780,
            minWidth: 760,
            minHeight: 560,
            layout: 'fit',
            items: [
                new Ext.BoxComponent({
                    height: '100%',
                    html: '<iframe title="NVFD 显卡控制" src="/webman/3rdparty/NVFD/index.html?v=1.0.0-0018" frameborder="0" width="100%" height="100%" style="display:block;background:#0b1220"></iframe>'
                })
            ]
        }, cfg);

        this.callParent([config]);
    }
});
