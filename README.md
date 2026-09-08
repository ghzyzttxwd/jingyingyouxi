# jingyingyouxi

《我的集团》Android APK 修改工程。

## 当前目标

1. 提高游戏内时间加速倍率。
2. 让订单数量随企业等级成长。
3. 广告奖励改为点击后直接发放奖励，不实际播放广告。

## 已确认的 APK 技术信息

- 引擎：Unity
- 脚本后端：IL2CPP
- 目标 ABI：arm64-v8a、armeabi-v7a
- 核心脚本程序集：`Assembly-CSharp.dll`
- IL2CPP 元数据：`assets/bin/Data/Managed/Metadata/global-metadata.dat`
- 原生代码：`lib/arm64-v8a/libil2cpp.so`、`lib/armeabi-v7a/libil2cpp.so`

已从元数据中确认存在以下关键类型/方法名：

- `TimeManager`
- `DingDanManager`
- `DingDanData`
- `RewardManager`
- `SendReward`

元数据还保留了部分原始脚本路径，例如：

- `Assets/Scripts/Ads/RewardManager.cs`
- `Assets/Scripts/Datas/DingDanData.cs`
- `Assets/Scripts/Managers/DingDanManager.cs`
- `Assets/Scripts/Managers/TimeManager.cs`

## 工作原则

- 原始 APK 不直接纳入 Git 版本管理。
- 仓库保存分析记录、dump、地址表、patch 脚本、构建/签名说明。
- 每个修改点先完成定位，再实施 patch，最后以真机安装和实际游戏行为为验收标准。
