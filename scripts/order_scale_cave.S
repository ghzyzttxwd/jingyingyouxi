.text
.global cave
.type cave,%function

// 这些符号值针对当前 arm64 libil2cpp.so 版本。
.extern PLAYERDATA_GOT
.extern GETLEVEL
.extern ADDORDER

// 输入保持 DingDanData.新增订单 的原调用约定：
// X0 = DingDanData instance
// W1 = 物品序号
// W2 = 数量
// W3 = 单价
// W4 = 剩余期限
// X5 = MethodInfo
//
// 处理：读取 PlayerData.获取公司等级()，把 W2 调整为：
// W2 = W2 + W2 * (level - 1) / 5
// 即每级约 +20%，然后调用原新增订单。

cave:
    stp x29, x30, [sp, #-0x40]!
    mov x29, sp
    stp x0, x1, [sp, #0x10]
    stp x2, x3, [sp, #0x20]
    stp x4, x5, [sp, #0x30]

    adrp x8, PLAYERDATA_GOT
    ldr  x8, [x8, :lo12:PLAYERDATA_GOT]
    ldr  x8, [x8]
    ldr  x8, [x8, #0xb8]
    ldr  x0, [x8]
    cbz  x0, 1f

    mov  x1, xzr
    bl   GETLEVEL

    ldp  x2, x3, [sp, #0x20]
    subs w0, w0, #1
    b.le 1f

    mov  w8, #5
    mul  w9, w2, w0
    sdiv w9, w9, w8
    add  w2, w2, w9
    str  x2, [sp, #0x20]

1:
    ldp x0, x1, [sp, #0x10]
    ldp x2, x3, [sp, #0x20]
    ldp x4, x5, [sp, #0x30]
    bl  ADDORDER

    ldp x29, x30, [sp], #0x40
    ret

.size cave, .-cave
