#!/usr/bin/env python3
import struct
import sys
from pathlib import Path

# 适用于当前 APK：Unity 2022.3.62f2c1 / Assembly-CSharp / arm64-v8a
# 地址均为当前版本 libil2cpp.so 的 VA，升级 APK 后必须重新定位。

TEXT_VA = 0x0FBE39C
TEXT_FO = 0x0FBA39C

# order_scale_cave.S 重新链接到 VA 0x12CA400 后的 108 字节机器码。
ORDER_CAVE = bytes.fromhex(
    "fd7bbca9fd030091e00701a9e20f02a9"
    "e41703a9a8b000b0087946f9080140f9"
    "085d40f9000140f9600100b4e1031faa"
    "942e0094e20f42a900040071cd000054"
    "a8008052497c001b290dc81a4200090b"
    "e21300f9e00741a9e20f42a9e41743a9"
    "8d0c0094fd7bc4a8c0035fd6"
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
        raise RuntimeError(f"{label}: 0x{va:X} expected {expected.hex()} got {old.hex()}")
    if len(expected) != len(replacement):
        raise RuntimeError(f"{label}: size mismatch")
    buf[fo:fo + len(replacement)] = replacement
    print(f"[ok] {label}: VA 0x{va:X}")


def main(src: str, dst: str):
    data = bytearray(Path(src).read_bytes())

    # 1. 激励广告直接发奖励。
    # V0.1-V0.3 直接从 播放广告() 跳 SendReward() 时把旧 x0 当成 RewardManager，
    # 但该调用链真正的 RewardManager 实例保存在 x19，导致点击广告入口 native 闪退。
    # 修复：先 mov x0,x19，再跳 SendReward()。
    patch(data, 0x12CA3EC, bytes.fromhex("fe0f1ef8"), bytes.fromhex("e00313aa"), "reward bypass: x19 -> x0")
    patch(data, 0x12CA3F0, bytes.fromhex("f44f01a9"), enc_branch(0x12CA3F0, 0x12C8A24, False), "reward bypass -> SendReward")

    # 原播放广告函数主体变为不可达区；订单 trampoline 从 0x12CA3F0 后移到 0x12CA400。
    cave_va = 0x12CA400
    cave_fo = va_to_fo(cave_va)
    data[cave_fo:cave_fo + len(ORDER_CAVE)] = ORDER_CAVE
    print(f"[ok] order-scale cave: VA 0x{cave_va:X}, {len(ORDER_CAVE)} bytes")

    # 订单发放调用点：BL DingDanData.新增订单 -> BL trampoline
    order_call = 0x12F7FE0
    original_add_order = 0x12CD694
    patch(data, order_call, enc_branch(order_call, original_add_order, True), enc_branch(order_call, cave_va, True), "order quantity growth")

    # 2. 高倍状态：0.5 秒阈值 -> 0.125 秒阈值（约 2x -> 8x）。
    patch(data, 0x132FAD4, bytes.fromhex("01102c1e"), bytes.fromhex("0110281e"), "high speed 8x")

    # 3. 倍速权限 getter 直接返回 true，避免再弹“观看广告获取倍速权限”。
    patch(data, 0x12D98AC, bytes.fromhex("fe0f1ef8f44f01a9"), bytes.fromhex("20008052c0035fd6"), "speed entitlement always true")

    # 4. TapTap 登录关闭，使用游戏内置离线分支。
    taptap_state_branch = 0x132EBF0
    taptap_offline_path = 0x132ED3C
    patch(data, taptap_state_branch, bytes.fromhex("680a0034"), enc_branch(taptap_state_branch, taptap_offline_path, False), "TapTap login disabled / built-in offline path")

    Path(dst).write_bytes(data)
    print(f"[done] {dst}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(f"usage: {sys.argv[0]} <original-libil2cpp.so> <patched-libil2cpp.so>")
    main(sys.argv[1], sys.argv[2])
