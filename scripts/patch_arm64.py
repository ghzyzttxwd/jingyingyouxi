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


def enc_ldr_s_literal(rt: int, src: int, dst: int) -> bytes:
    delta = dst - src
    if delta % 4:
        raise ValueError("literal unaligned")
    imm = delta // 4
    if not (-(1 << 18) <= imm < (1 << 18)):
        raise ValueError("literal out of range")
    word = 0x1C000000 | ((imm & 0x7FFFF) << 5) | (rt & 31)
    return struct.pack("<I", word)


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
    # RewardManager 实例在此调用链保存在 x19，先移动到 x0，再跳原 SendReward()。
    patch(data, 0x12CA3EC, bytes.fromhex("fe0f1ef8"), bytes.fromhex("e00313aa"), "reward bypass: x19 -> x0")
    patch(data, 0x12CA3F0, bytes.fromhex("f44f01a9"), enc_branch(0x12CA3F0, 0x12C8A24, False), "reward bypass -> SendReward")

    # 原播放广告函数主体变为不可达区，用作订单成长 trampoline。
    cave_va = 0x12CA400
    cave_fo = va_to_fo(cave_va)
    data[cave_fo:cave_fo + len(ORDER_CAVE)] = ORDER_CAVE
    print(f"[ok] order-scale cave: VA 0x{cave_va:X}, {len(ORDER_CAVE)} bytes")

    # 订单发放调用点：BL DingDanData.新增订单 -> BL trampoline。
    order_call = 0x12F7FE0
    original_add_order = 0x12CD694
    patch(data, order_call, enc_branch(order_call, original_add_order, True), enc_branch(order_call, cave_va, True), "order quantity growth")

    # 2. 高倍状态改为约 6x。
    # 普通状态阈值为 1.0 秒，高倍状态读取 1/6 秒 float literal。
    # 0x12CA46C 位于订单 trampoline 的 RET 之后，且原广告函数已不可达。
    speed_literal_va = 0x12CA46C
    patch(data, speed_literal_va, bytes.fromhex("08e040b9"), struct.pack("<f", 1.0 / 6.0), "6x threshold literal")
    patch(data, 0x132FAD4, bytes.fromhex("01102c1e"), enc_ldr_s_literal(1, 0x132FAD4, speed_literal_va), "high speed 6x")

    # 3. 原右上角按钮显示的是“点击后将切换到的下一档”。
    # 改为显示当前实际倍率：状态 0 -> 1.0X；状态 1 -> 6.0X。
    patch(data, 0x132BD18, bytes.fromhex("a8000034"), bytes.fromhex("a8000035"), "speed label shows current state")

    # 4. 倍速权限 getter 直接返回 true，避免再弹“观看广告获取倍速权限”。
    patch(data, 0x12D98AC, bytes.fromhex("fe0f1ef8f44f01a9"), bytes.fromhex("20008052c0035fd6"), "speed entitlement always true")

    # 5. TapTap 登录关闭，使用游戏内置离线分支。
    taptap_state_branch = 0x132EBF0
    taptap_offline_path = 0x132ED3C
    patch(data, taptap_state_branch, bytes.fromhex("680a0034"), enc_branch(taptap_state_branch, taptap_offline_path, False), "TapTap login disabled / built-in offline path")

    Path(dst).write_bytes(data)
    print(f"[done] {dst}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(f"usage: {sys.argv[0]} <original-libil2cpp.so> <patched-libil2cpp.so>")
    main(sys.argv[1], sys.argv[2])
