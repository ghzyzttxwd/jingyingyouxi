# jingyingyouxi

《我的集团》Android APK 修改工程。

## V0.1 当前状态

已经生成 **arm64 真机测试包**，等待设备验收。

当前三个修改：

1. 原高倍状态约 2× → 测试版约 **8×**。
2. 订单数量按公司等级成长，测试公式为 `原数量 + 原数量 × (公司等级 - 1) / 5`。
3. 激励广告入口直接跳转游戏原本的 `SendReward()`，不实际播放广告。

目前只 patch `arm64-v8a`；`armeabi-v7a` 暂保留原版。

## APK 技术信息

- 原版本：`1.0.9` / versionCode `10`
- 引擎：Unity `2022.3.62f2c1`
- 脚本后端：IL2CPP
- metadata：v31
- 目标 ABI：arm64-v8a、armeabi-v7a
- 核心脚本程序集：`Assembly-CSharp.dll`
- IL2CPP 元数据：`assets/bin/Data/Managed/Metadata/global-metadata.dat`
- 原生代码：`lib/arm64-v8a/libil2cpp.so`、`lib/armeabi-v7a/libil2cpp.so`

关键类型/方法已定位：

- `TimeManager.时间流逝逻辑`
- `TimeManager.切换时间速度`
- `DingDanManager.订单发放逻辑`
- `DingDanData.新增订单`
- `PlayerData.获取公司等级`
- `RewardManager.播放广告`
- `RewardManager.SendReward`

## 仓库内容

- `docs/修改需求.md`：V0.1 功能目标、测试参数和验收项。
- `docs/逆向定位.md`：token、VA、patch 地址、签名和本地验证记录。
- `scripts/patch_arm64.py`：arm64 `libil2cpp.so` patch。
- `scripts/order_scale_cave.S`：订单成长 trampoline 汇编源码。
- `scripts/repack_aligned.py`：APK 重打包并保持 `resources.arsc` 4-byte alignment。
- `scripts/apk_v2_sign.py`：APK Signature Scheme v2 签名与自检。

## 验收原则

静态分析、反汇编、ZIP 和签名自检均不能替代真机验收。V0.1 必须在 Android 设备上确认：

- 能安装、启动且不闪退；
- 高倍速实际生效；
- 订单数量随等级成长且金额正常；
- 广告奖励点击后直接发放且不重复；

全部通过后，才标记为完成。
