#!/usr/bin/env python3
import struct
import sys
from pathlib import Path

# 适用于当前 APK：Unity 2022.3.62f2c1 / Assembly-CSharp / arm64-v8a
# 地址均为当前版本 libil2cpp.so 的 VA，升级 APK 后必须重新定位。

TEXT_VA = 0x0FBE39C
TEXT_FO = 0x0FBA39C

# order_scale_cave.S 在 VA 0x12CA3F0 链接后的 108 字节机器码。
ORDER_CAVE = bytes.fromhex(
    "fd7bbca9fd030091e00701a9e20f02a9"
    "e41703a9a8b000b0087946f9080140f9"
    "085d40f9000140f9600100b4e1031faa"
    "982e0094e20f42a900040071cd000054"
    "a8008052497c001b290dc81a4200090b"
    "e21300f9e00741a9e20f42a9e41743a9"
    "910c0094fd7bc4a8c0035fd6"
)


def va_to_fo(va: int) -> int:
    return TEXT_FO + (va - TEXT_VA)


def enc_branch(src: int, dst: int, link: bool) -> bytes:
    delta = dst - src
    if delta % 4:
        raise ValueError("unaligned branch")
    imm = delta // 4
    if not (-(1 << 25) <= imm < (1 << 25)):
        raise ValueError("branch out of range")
    op = 0x94000000 if link else 0x14000000
    return struct.pack("<I", op | (imm & 0x03FFFFFF))


def patch(buf: bytearray, va: int, expected: bytes, replacement: bytes, label: str):
    fo = va_to_fo(va)
    old = bytes(buf[fo:fo + len(expected)])
    if old != expected:
        raise RuntimeError(
            f"{label}: 0x{va:X} expected {expected.hex()} got {old.hex()}"
        )
    if len(expected) != len(replacement):
        raise RuntimeError(f"{label}: size mismatch")
    buf[fo:fo + len(replacement)] = replacement
    print(f"[ok] {label}: VA 0x{va:X}")


def main(src: str, dst: str):
    data = bytearray(Path(src).read_bytes())

    # 1. RewardManager.播放广告() -> RewardManager.SendReward()
    reward_play = 0x12CA3EC
    reward_send = 0x12C8A24
    patch(
        data,
        reward_play,
        bytes.fromhex("fe0f1ef8"),
        enc_branch(reward_play, reward_send, False),
        "rewarded-ad bypass",
    )

    # 2. 复用已经不可达的播放广告函数主体作为订单成长 trampoline。
    cave_va = 0x12CA3F0
    cave_fo = va_to_fo(cave_va)
    data[cave_fo:cave_fo + len(ORDER_CAVE)] = ORDER_CAVE
    print(f"[ok] order-scale cave: VA 0x{cave_va:X}, {len(ORDER_CAVE)} bytes")

    # 订单发放调用点：BL DingDanData.新增订单 -> BL trampoline
    order_call = 0x12F7FE0
    original_add_order = 0x12CD694
    patch(
        data,
        order_call,
        enc_branch(order_call, original_add_order, True),
        enc_branch(order_call, cave_va, True),
        "order quantity growth",
    )

    # 3. TimeManager 高倍状态：0.5 秒阈值 -> 0.125 秒阈值（约 2x -> 8x）
    patch(
        data,
        0x132FAD4,
        bytes.fromhex("01102c1e"),  # FMOV S1,#0.5
        bytes.fromhex("0110281e"),  # FMOV S1,#0.125
        "high speed 8x",
    )

    # 4. 重签名 APK 无法通过 TapTap 的“包名 + 原开发者签名”校验。
    # 游戏自身 TapTapLoginManager.Start 的状态机已包含官方离线分支：
    # TapTap登录状态 == false 时不初始化 TapSDK，并隐藏开始界面的登录按钮。
    # 这里把条件分支改成无条件进入该离线分支，不伪造 TapTap 账号。
    taptap_state_branch = 0x132EBF0
    taptap_offline_path = 0x132ED3C
    patch(
        data,
        taptap_state_branch,
        bytes.fromhex("680a0034"),  # CBZ W8, offline_path
        enc_branch(taptap_state_branch, taptap_offline_path, False),
        "TapTap login disabled / built-in offline path",
    )

    Path(dst).write_bytes(data)
    print(f"[done] {dst}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(f"usage: {sys.argv[0]} <original-libil2cpp.so> <patched-libil2cpp.so>")
    main(sys.argv[1], sys.argv[2])
