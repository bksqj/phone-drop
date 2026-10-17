"""Мини-генератор QR-кода без библиотек: байтовый режим, уровень коррекции L, версии 1-5
(до 106 символов - для адреса хватает с запасом). Печатает код в терминал."""

# версия: (сколько байт данных, сколько байт коррекции ошибок) для уровня L, один блок
VERSIONS = {1: (19, 7), 2: (34, 10), 3: (55, 15), 4: (80, 20), 5: (108, 26)}

# таблицы поля Галуа GF(256) для кода Рида-Соломона
EXP, LOG = [0] * 512, [0] * 256
_x = 1
for _i in range(255):
    EXP[_i], LOG[_x] = _x, _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    EXP[_i] = EXP[_i - 255]


def _mul(a, b):
    return 0 if a == 0 or b == 0 else EXP[LOG[a] + LOG[b]]


def _rs(data, n):
    """байты коррекции ошибок Рида-Соломона"""
    gen = [1]
    for i in range(n):                                  # (x - a^0)(x - a^1)...(x - a^(n-1))
        gen = [a ^ _mul(b, EXP[i]) for a, b in zip(gen + [0], [0] + gen)]
    rem = list(data) + [0] * n
    for i in range(len(data)):
        c = rem[i]
        if c:
            for j in range(1, n + 1):
                rem[i + j] ^= _mul(gen[j], c)
    return rem[len(data):]


MASKS = [
    lambda x, y: (x + y) % 2 == 0,
    lambda x, y: y % 2 == 0,
    lambda x, y: x % 3 == 0,
    lambda x, y: (x + y) % 3 == 0,
    lambda x, y: (x // 3 + y // 2) % 2 == 0,
    lambda x, y: x * y % 2 + x * y % 3 == 0,
    lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
    lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
]


def make(text):
    """возвращает матрицу QR-кода: список строк из True (чёрный) / False (белый)"""
    raw = text.encode('utf-8')
    ver = next((v for v, (cap, _) in VERSIONS.items() if len(raw) + 2 <= cap), None)
    if ver is None:
        raise ValueError('слишком длинный текст для QR')
    cap, ecn = VERSIONS[ver]

    # 1) биты данных: режим "байты" 0100, длина 8 бит, сами байты, терминатор, добивка
    bits = '0100' + format(len(raw), '08b') + ''.join(format(b, '08b') for b in raw)
    bits += '0' * min(4, cap * 8 - len(bits))
    bits += '0' * (-len(bits) % 8)
    data = [int(bits[i:i + 8], 2) for i in range(0, len(bits), 8)]
    k = 0
    while len(data) < cap:                              # добивка чередующимися 0xEC 0x11
        data.append((0xEC, 0x11)[k % 2])
        k += 1
    codewords = data + _rs(data, ecn)

    # 2) служебные узоры
    size = 17 + 4 * ver
    m = [[False] * size for _ in range(size)]
    fn = [[False] * size for _ in range(size)]          # клетки служебных узоров - данные туда не пишем

    def put(x, y, dark):
        m[y][x], fn[y][x] = dark, True

    for i in range(size):                               # линии синхронизации
        put(6, i, i % 2 == 0)
        put(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):   # три больших квадрата по углам
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < size and 0 <= y < size:
                    d = max(abs(dx), abs(dy))
                    put(x, y, d not in (2, 4))
    if ver >= 2:                                        # маленький квадрат выравнивания
        p = 4 * ver + 10
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                put(p + dx, p + dy, max(abs(dx), abs(dy)) != 1)

    def put_format(mask):
        d = (1 << 3) | mask                             # уровень L = 01
        rem = d
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        f = ((d << 10) | rem) ^ 0x5412
        b = lambda i: (f >> i) & 1 == 1
        for i in range(6):
            put(8, i, b(i))
        put(8, 7, b(6)); put(8, 8, b(7)); put(7, 8, b(8))
        for i in range(9, 15):
            put(14 - i, 8, b(i))
        for i in range(8):
            put(size - 1 - i, 8, b(i))
        for i in range(8, 15):
            put(8, size - 15 + i, b(i))
        put(8, size - 8, True)                          # обязательный тёмный модуль

    put_format(0)                                       # резервируем место под формат

    # 3) раскладываем биты змейкой снизу вверх по парам столбцов
    allbits = ''.join(format(c, '08b') for c in codewords)
    i, right = 0, size - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(size):
            for j in range(2):
                x = right - j
                y = size - 1 - vert if ((right + 1) & 2) == 0 else vert
                if not fn[y][x] and i < len(allbits):
                    m[y][x] = allbits[i] == '1'
                    i += 1
        right -= 2

    # 4) пробуем все 8 масок, берём ту, где меньше штраф
    def penalty(g):
        s = 0
        for rows in (g, list(zip(*g))):
            for row in rows:                            # длинные одноцветные отрезки
                run = 1
                for a, b in zip(row, row[1:]):
                    run = run + 1 if a == b else 1
                    if run == 5: s += 3
                    elif run > 5: s += 1
        for y in range(size - 1):                       # квадраты 2x2 одного цвета
            for x in range(size - 1):
                if g[y][x] == g[y][x + 1] == g[y + 1][x] == g[y + 1][x + 1]:
                    s += 3
        dark = sum(map(sum, g)) * 100 // (size * size)  # баланс чёрного и белого
        return s + abs(dark - 50) // 5 * 10

    best = None
    for k, f in enumerate(MASKS):
        put_format(k)
        g = [[m[y][x] ^ (not fn[y][x] and f(x, y)) for x in range(size)] for y in range(size)]
        p = penalty(g)
        if best is None or p < best[0]:
            best = (p, g)
    return best[1]


def terminal(text, border=2):
    """QR в терминал: два ряда модулей на строку символом ▀, чёрное на белом"""
    g = make(text)
    n = len(g) + 2 * border
    cell = lambda x, y: 0 <= y - border < len(g) and 0 <= x - border < len(g) and g[y - border][x - border]
    lines = []
    for y in range(0, n, 2):
        s = ''
        for x in range(n):
            top, bot = cell(x, y), y + 1 < n and cell(x, y + 1)
            s += '\033[%d;%dm▀' % (30 if top else 97, 40 if bot else 107)
        lines.append(s + '\033[0m')
    return '\n'.join(lines)


if __name__ == '__main__':
    import sys
    print(terminal(sys.argv[1] if len(sys.argv) > 1 else 'http://172.20.10.2:8000'))
