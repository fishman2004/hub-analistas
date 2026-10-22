"""QR Code em SVG, em Python puro, para abrir o Hub no celular (fase 18).

Segue a norma do QR Code (ISO/IEC 18004) só no que o Hub precisa: texto curto (um endereço), modo byte,
correção de erro nível M (aguenta ~15% do desenho sujo ou cortado) e versões 1 a 10 (até 213 letras).
Sem biblioteca nova: são poucas contas, e o resultado é conferido nos testes.
"""

# por versão (1 a 10), nível M: (bytes de correção por bloco, quantidade de blocos)
_EC_M = {1: (10, 1), 2: (16, 1), 3: (26, 1), 4: (18, 2), 5: (24, 2),
         6: (16, 4), 7: (18, 4), 8: (22, 4), 9: (22, 5), 10: (26, 5)}
_FORMAT_M = 0  # bits do nível M no formato
MAX_VERSION = 10


def _gf_mul(x: int, y: int) -> int:
    """Multiplicação no corpo de 256 elementos do QR Code (polinômio 0x11D)."""
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree: int) -> list[int]:
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 0x02)
    return result


def _rs_remainder(data: list[int], divisor: list[int]) -> list[int]:
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _gf_mul(coef, factor)
    return result


def _raw_modules(version: int) -> int:
    """Quantos módulos sobram para dados depois dos desenhos fixos."""
    result = (16 * version + 128) * version + 64
    if version >= 2:
        n = version // 7 + 2
        result -= (25 * n - 10) * n - 55
        if version >= 7:
            result -= 36
    return result


def _data_capacity(version: int) -> int:
    ec, blocks = _EC_M[version]
    return _raw_modules(version) // 8 - ec * blocks


def _alignment_positions(version: int) -> list[int]:
    if version == 1:
        return []
    n = version // 7 + 2
    size = version * 4 + 17
    step = (version * 8 + n * 3 + 5) // (n * 4 - 4) * 2
    return [6] + sorted(size - 7 - i * step for i in range(n - 1))


def _codewords(data: bytes, version: int) -> list[int]:
    bits: list[int] = []

    def put(value: int, length: int) -> None:
        bits.extend((value >> i) & 1 for i in reversed(range(length)))

    put(0b0100, 4)  # modo byte
    put(len(data), 8 if version <= 9 else 16)
    for b in data:
        put(b, 8)
    capacity = _data_capacity(version) * 8
    put(0, min(4, capacity - len(bits)))
    put(0, -len(bits) % 8)
    pad = 0xEC
    while len(bits) < capacity:
        put(pad, 8)
        pad ^= 0xEC ^ 0x11
    words = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]

    # divide em blocos, calcula a correção de cada um e intercala
    ec_len, num_blocks = _EC_M[version]
    raw = _raw_modules(version) // 8
    short_blocks = num_blocks - raw % num_blocks
    short_len = raw // num_blocks
    divisor = _rs_divisor(ec_len)
    blocks, k = [], 0
    for i in range(num_blocks):
        size = short_len - ec_len + (0 if i < short_blocks else 1)
        dat = words[k:k + size]
        k += size
        ecc = _rs_remainder(dat, divisor)
        if i < short_blocks:
            dat = dat + [0]
        blocks.append(dat + ecc)
    result = []
    for i in range(len(blocks[0])):
        for j, block in enumerate(blocks):
            if i != short_len - ec_len or j >= short_blocks:
                result.append(block[i])
    return result


_MASKS = (
    lambda x, y: (x + y) % 2 == 0,
    lambda x, y: y % 2 == 0,
    lambda x, y: x % 3 == 0,
    lambda x, y: (x + y) % 3 == 0,
    lambda x, y: (x // 3 + y // 2) % 2 == 0,
    lambda x, y: x * y % 2 + x * y % 3 == 0,
    lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
    lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
)


class _Matrix:
    def __init__(self, version: int) -> None:
        self.version = version
        self.size = version * 4 + 17
        self.dark = [[False] * self.size for _ in range(self.size)]
        self.fixed = [[False] * self.size for _ in range(self.size)]

    def set_fixed(self, x: int, y: int, dark: bool) -> None:
        self.dark[y][x] = dark
        self.fixed[y][x] = True

    def draw_patterns(self) -> None:
        n = self.size
        for i in range(n):  # linhas de tempo
            self.set_fixed(6, i, i % 2 == 0)
            self.set_fixed(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):  # os três quadrados dos cantos
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        self.set_fixed(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = _alignment_positions(self.version)
        last = len(pos) - 1
        for i, cx in enumerate(pos):
            for j, cy in enumerate(pos):
                if (i, j) in ((0, 0), (0, last), (last, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.set_fixed(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)
        self.draw_format(0)
        if self.version >= 7:
            rem = self.version
            for _ in range(12):
                rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
            bits = self.version << 12 | rem
            for i in range(18):
                bit = (bits >> i) & 1 == 1
                a, b = n - 11 + i % 3, i // 3
                self.set_fixed(a, b, bit)
                self.set_fixed(b, a, bit)

    def draw_format(self, mask: int) -> None:
        data = _FORMAT_M << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        bit = lambda i: (bits >> i) & 1 == 1
        n = self.size
        for i in range(6):
            self.set_fixed(8, i, bit(i))
        self.set_fixed(8, 7, bit(6))
        self.set_fixed(8, 8, bit(7))
        self.set_fixed(7, 8, bit(8))
        for i in range(9, 15):
            self.set_fixed(14 - i, 8, bit(i))
        for i in range(8):
            self.set_fixed(n - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.set_fixed(8, n - 15 + i, bit(i))
        self.set_fixed(8, n - 8, True)  # o módulo sempre escuro

    def draw_data(self, words: list[int]) -> None:
        n, i = self.size, 0
        right = n - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(n):
                for j in range(2):
                    x = right - j
                    upward = (right + 1) & 2 == 0
                    y = n - 1 - vert if upward else vert
                    if not self.fixed[y][x] and i < len(words) * 8:
                        self.dark[y][x] = (words[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            right -= 2

    def apply_mask(self, mask: int) -> None:
        test = _MASKS[mask]
        for y in range(self.size):
            for x in range(self.size):
                if not self.fixed[y][x] and test(x, y):
                    self.dark[y][x] = not self.dark[y][x]

    def penalty(self) -> int:
        """Pontuação da norma: quanto menor, mais fácil para a câmera ler."""
        n, score = self.size, 0
        lines = self.dark + [[self.dark[y][x] for y in range(n)] for x in range(n)]
        for line in lines:
            run, prev = 0, None
            for cell in line:
                run = run + 1 if cell == prev else 1
                prev = cell
                if run == 5:
                    score += 3
                elif run > 5:
                    score += 1
            text = "0000" + "".join("1" if c else "0" for c in line) + "0000"
            score += 40 * (text.count("00001011101") + text.count("10111010000"))
        for y in range(n - 1):
            for x in range(n - 1):
                c = self.dark[y][x]
                if c == self.dark[y][x + 1] == self.dark[y + 1][x] == self.dark[y + 1][x + 1]:
                    score += 3
        dark = sum(map(sum, self.dark))
        score += 10 * (abs(dark * 20 - n * n * 10) // (n * n))
        return score


def qr_matrix(text: str) -> list[list[bool]]:
    """A grade do QR Code (True = quadradinho escuro), sem a margem."""
    data = text.encode("utf-8")
    version = next((v for v in range(1, MAX_VERSION + 1)
                    if 4 + (8 if v <= 9 else 16) + len(data) * 8 <= _data_capacity(v) * 8), None)
    if version is None:
        raise ValueError("Texto comprido demais para o QR Code.")
    words = _codewords(data, version)
    best = None
    for mask in range(8):
        m = _Matrix(version)
        m.draw_patterns()
        m.draw_data(words)
        m.apply_mask(mask)
        m.draw_format(mask)
        score = m.penalty()
        if best is None or score < best[0]:
            best = (score, m)
    return best[1].dark


def qr_svg(text: str, border: int = 4) -> str:
    """O QR Code como SVG (preto no branco, com a margem que a câmera precisa)."""
    grid = qr_matrix(text)
    n = len(grid) + border * 2
    path = "".join(f"M{x + border},{y + border}h1v1h-1z"
                   for y, row in enumerate(grid) for x, cell in enumerate(row) if cell)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" shape-rendering="crispEdges" '
            f'role="img" aria-label="QR Code"><rect width="{n}" height="{n}" fill="#fff"/>'
            f'<path d="{path}" fill="#000"/></svg>')
