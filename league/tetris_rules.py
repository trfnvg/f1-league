"""Bounded, authoritative replay of Pit Stack rules v1 (tetris-engine.js).

Only the seed issued by the server and ordered input ticks affect a result.
No client-supplied score, board, level, or piece sequence is trusted.
"""
STEP = 1000 / 60
VERSION = 1
MAX_TICKS = 60 * 60 * 60 * 4  # Four active hours; explicit client/server resource bound.
MAX_INPUTS = 30_000
FRAMES = (48,43,38,33,28,23,18,13,8,6,5,5,5,4,4,4,3,3,3,2,2,2,2,2,2,2,2,2,2,1)
SHAPES = (
    ((0,0,0,0),(1,1,1,1),(0,0,0,0),(0,0,0,0)),
    ((1,0,0),(1,1,1),(0,0,0)), ((0,0,1),(1,1,1),(0,0,0)),
    ((1,1),(1,1)), ((0,1,1),(1,1,0),(0,0,0)),
    ((0,1,0),(1,1,1),(0,0,0)), ((1,1,0),(0,1,1),(0,0,0)),
)
ACTIONS = ("left", "right", "rotate", "rotateCCW", "down", "drop")


class ReplayError(ValueError):
    pass


class Game:
    def __init__(self, seed):
        self.seed = seed
        self.board = [[None]*10 for _ in range(20)]
        self.score = self.lines = 0
        self.level = 1
        self.phase = "running"
        self.clearing = []
        self.clear_clock = 0
        self.next = self.random_type()
        self.spawn()

    def random_type(self):
        self.seed = (1664525*self.seed+1013904223) & 0xFFFFFFFF
        return self.seed*7 >> 32

    def spawn(self):
        self.kind = self.next
        self.next = self.random_type()
        self.matrix = [list(row) for row in SHAPES[self.kind]]
        self.x, self.y = (10-len(self.matrix))//2, -1
        self.fall_clock = self.lock_clock = self.lock_resets = 0
        if not self.fits(self.matrix, self.x, self.y):
            self.phase = "over"

    def fits(self, matrix, x, y):
        for dy, row in enumerate(matrix):
            for dx, occupied in enumerate(row):
                if occupied and (x+dx < 0 or x+dx >= 10 or y+dy >= 20 or
                                 (y+dy >= 0 and self.board[y+dy][x+dx] is not None)):
                    return False
        return True

    def grounded(self):
        return not self.fits(self.matrix, self.x, self.y+1)

    def reset_lock(self, grounded):
        if grounded and self.lock_resets < 10:
            self.lock_clock = 0
            self.lock_resets += 1

    def action(self, action):
        if self.phase != "running":
            raise ReplayError("Ввод вне активной фигуры.")
        if action in (0,1):
            x = self.x + (-1 if action == 0 else 1)
            if self.fits(self.matrix, x, self.y):
                self.reset_lock(self.grounded())
                self.x = x
        elif action in (2,3) and self.kind != 3:
            matrix = self.matrix
            for _ in range(1 if action == 2 else 3):
                matrix = [list(row) for row in zip(*matrix[::-1])]
            for offset in (0,-1,1,-2,2):
                if self.fits(matrix, self.x+offset, self.y):
                    self.reset_lock(self.grounded())
                    self.matrix, self.x = matrix, self.x+offset
                    break
        elif action == 4:
            if self.fits(self.matrix, self.x, self.y+1):
                self.y += 1
                self.score += 1
                self.lock_clock = 0
        elif action == 5:
            while not self.grounded():
                self.y += 1
                self.score += 2
            self.lock()

    def lock(self):
        for dy, row in enumerate(self.matrix):
            for dx, occupied in enumerate(row):
                if not occupied:
                    continue
                if self.y+dy < 0:
                    self.phase = "over"
                    return
        for dy, row in enumerate(self.matrix):
            for dx, occupied in enumerate(row):
                if occupied:
                    self.board[self.y+dy][self.x+dx] = self.kind
        self.clearing = [y for y,row in enumerate(self.board) if all(v is not None for v in row)]
        if self.clearing:
            self.phase, self.clear_clock = "clearing", 0
        else:
            self.spawn()

    def update(self):
        if self.phase == "clearing":
            self.clear_clock += STEP
            if self.clear_clock >= 180:
                count = len(self.clearing)
                self.board = [row for y,row in enumerate(self.board) if y not in self.clearing]
                self.board = [[None]*10 for _ in range(count)]+self.board
                self.score += (0,40,100,300,1200)[count]*self.level
                self.lines += count
                self.level = 1+self.lines//10
                self.clearing = []
                self.phase = "running"
                self.spawn()
            return
        if self.grounded():
            self.lock_clock += STEP
            if self.lock_clock >= max(220,350-(self.level-1)*8):
                self.lock()
            return
        self.lock_clock = 0
        self.fall_clock += STEP
        gravity = FRAMES[min(29,self.level-1)]*1000/60
        while self.fall_clock+1e-7 >= gravity and not self.grounded():
            self.y += 1
            self.lock_clock = 0
            self.fall_clock = max(0,self.fall_clock-gravity)


def verify(seed, ticks, inputs, elapsed_seconds):
    if (type(ticks) is not int or not 0 <= ticks <= MAX_TICKS or
            not isinstance(inputs,list) or len(inputs) > MAX_INPUTS):
        raise ReplayError("Некорректная длительность или размер повтора.")
    if ticks > max(0,elapsed_seconds)*60+120:
        raise ReplayError("Повтор длиннее реального времени попытки.")
    last_tick, same_tick = -1, 0
    for event in inputs:
        if (not isinstance(event,list) or len(event) != 2 or any(type(v) is not int for v in event)
                or not 0 <= event[0] <= ticks or event[0] < last_tick or not 0 <= event[1] < len(ACTIONS)):
            raise ReplayError("Некорректный ввод в повторе.")
        same_tick = same_tick+1 if event[0] == last_tick else 1
        if same_tick > 8:
            raise ReplayError("Слишком много команд в одном кадре.")
        last_tick = event[0]
    game, index = Game(seed), 0
    for tick in range(ticks+1):
        while index < len(inputs) and inputs[index][0] == tick:
            game.action(inputs[index][1])
            index += 1
        if tick == ticks:
            break
        if game.phase == "over":
            raise ReplayError("Лишние кадры после окончания игры.")
        game.update()
    if game.phase != "over" and ticks != MAX_TICKS and len(inputs) != MAX_INPUTS:
        raise ReplayError("Попытка ещё не завершена.")
    if not 0 <= game.score <= 2_147_483_647:
        raise ReplayError("Результат вне допустимого диапазона.")
    return game.score
