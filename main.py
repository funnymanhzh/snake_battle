"""
贪吃蛇大作战 - Snake Battle
======================

玩法：
- 玩家（WASD/方向键）控制绿色蛇，其余 4 条 AI 蛇自动寻食
- 地图上常驻 8 个食物，吃到身体 +1
- 碰撞规则（核心）：
    * 蛇头 vs 蛇头：更长的蛇获胜，短的死亡、整个身体化成食物；等长同归于尽
    * 蛇头 vs 蛇身：大蛇撞小蛇身时，大蛇截取撞击点之后的小蛇身作为补给，
      小蛇保留「头 → 撞击点」前段，其余化成食物；小蛇头撞大蛇身 → 小蛇死亡
    * 撞墙：死亡，整个身体化成食物
    * 撞到自己身体：不 Game Over（直接穿过）
- 加速：按住与当前方向相同的方向键 → 加速到上限

按 R 重启，Q 退出。
"""
import asyncio
import pygame
import random
import sys
from collections import deque

# ==================== Constants ====================
CELL_SIZE = 22
GRID_WIDTH = 38
GRID_HEIGHT = 26
WINDOW_WIDTH = CELL_SIZE * GRID_WIDTH
HUD_HEIGHT = 76
GAME_HEIGHT = CELL_SIZE * GRID_HEIGHT
WINDOW_HEIGHT = HUD_HEIGHT + GAME_HEIGHT
GAME_OFFSET_Y = HUD_HEIGHT

# Colors
BLACK        = (0, 0, 0)
WHITE        = (245, 245, 245)
GRAY         = (90, 90, 90)
RED          = (220, 30, 60)
GREEN        = (60, 210, 90)
DARK_GREEN   = (25, 110, 45)
BLUE         = (60, 140, 255)
DARK_BLUE    = (20, 75, 180)
YELLOW       = (255, 215, 0)
PURPLE       = (190, 90, 230)
DARK_PURPLE  = (115, 35, 155)
ORANGE       = (255, 145, 45)
DARK_ORANGE  = (185, 95, 5)
CYAN         = (60, 220, 220)
DARK_CYAN    = (0, 135, 135)
PINK         = (255, 105, 185)
DARK_PINK    = (185, 70, 130)

SNAKE_THEMES = [
    {'body': GREEN,  'head': (255, 245, 110), 'dark': DARK_GREEN,  'name': 'YOU'},
    {'body': BLUE,   'head': (130, 220, 255), 'dark': DARK_BLUE,   'name': 'Azure'},
    {'body': PURPLE, 'head': (245, 155, 255), 'dark': DARK_PURPLE, 'name': 'Violet'},
    {'body': ORANGE, 'head': (255, 220, 135), 'dark': DARK_ORANGE, 'name': 'Ember'},
    {'body': CYAN,   'head': (185, 255, 255), 'dark': DARK_CYAN,   'name': 'Aqua'},
    {'body': PINK,   'head': (255, 205, 230), 'dark': DARK_PINK,   'name': 'Rose'},
]

BASE_SPEED = 5.0
BOOST_SPEED = 12.0
SMOOTH_RATE = 8.0
MAX_STEPS_PER_FRAME = 4

NUM_FOOD = 8

# NPC 蛇：开局随机 8-10 条，每条长度 1-5 随机
INITIAL_NPC_RANGE = (15, 20)
INITIAL_NPC_LEN_RANGE = (1, 10)
# 当活 NPC 数低于这个值时，食物有机会孵化成新 NPC（自动补充）
MIN_NPC_COUNT = 10
# 孵化检查周期（秒）
NPC_SPAWN_CHECK_INTERVAL = 1.0

KEY_DIR_MAP = {
    pygame.K_UP:    (0, -1),
    pygame.K_DOWN:  (0, 1),
    pygame.K_LEFT:  (-1, 0),
    pygame.K_RIGHT: (1, 0),
}
ALL_DIRS = [(0, -1), (0, 1), (-1, 0), (1, 0)]


# ==================== Snake ====================
class Snake:
    def __init__(self, head_x, head_y, direction, theme, is_ai=False, name="Snake"):
        self.body = deque([(head_x, head_y)])
        self.direction = direction
        self.next_direction = direction
        self.theme = theme
        self.is_ai = is_ai
        self.name = name
        self.alive = True
        self.growing = False
        self.current_speed = BASE_SPEED
        self.move_accumulator = 0.0
        self.score = 0
        self.boosting = False
        self.death_reason = ""

    @property
    def head(self):
        return self.body[0]

    @property
    def length(self):
        return len(self.body)

    def get_body_set(self):
        return set(self.body)

    def set_direction(self, new_dir):
        # 不允许 180° 反向
        if (new_dir[0] != -self.direction[0] or new_dir[1] != -self.direction[1]):
            self.next_direction = new_dir

    def step(self, food_set):
        self.direction = self.next_direction
        hx, hy = self.body[0]
        new_head = (hx + self.direction[0], hy + self.direction[1])
        self.body.appendleft(new_head)
        # 吃到食物 或 本帧已标记增长 → 不 pop 尾巴
        if (new_head in food_set) or self.growing and random.random() < 0.1:
            self.growing = False
        else:
            self.body.pop()
        return new_head


# ==================== Game ====================
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("🐍 贪吃蛇大作战")
        self.clock = pygame.time.Clock()
        self.font_huge = pygame.font.Font(None, 80)
        self.font_large = pygame.font.Font(None, 44)
        self.font_medium = pygame.font.Font(None, 30)
        self.font_small = pygame.font.Font(None, 22)
        self.font_tiny = pygame.font.Font(None, 17)
        self.reset()

    def reset(self):
        # 玩家：左侧居中，初始向右
        self.player = Snake(
            GRID_WIDTH // 5, GRID_HEIGHT // 2,
            (1, 0),
            SNAKE_THEMES[0],
            is_ai=False,
            name="YOU"
        )

        # AI 蛇：随机 8-10 条，长度 1-5 随机，分散起手
        self.ai_snakes = []
        target_count = random.randint(*INITIAL_NPC_RANGE)
        occupied = {self.player.head}
        npc_index = 0
        attempts = 0
        while npc_index < target_count and attempts < 2000:
            attempts += 1
            head = (random.randint(2, GRID_WIDTH - 3),
                    random.randint(2, GRID_HEIGHT - 3))
            if head in occupied:
                continue
            direction = random.choice(ALL_DIRS)
            init_len = random.randint(*INITIAL_NPC_LEN_RANGE)
            # 蛇身从头反方向延伸，遇到边界/已有蛇就缩短
            body = [head]
            cx, cy = head
            dx, dy = -direction[0], -direction[1]
            for _ in range(init_len - 1):
                nx, ny = cx + dx, cy + dy
                if nx < 1 or nx >= GRID_WIDTH - 1 or ny < 1 or ny >= GRID_HEIGHT - 1:
                    break
                if (nx, ny) in occupied:
                    break
                body.append((nx, ny))
                cx, cy = nx, ny
            # 至少要 1 节；尝试下一组位置
            if not body:
                continue
            # 主题循环使用
            theme = SNAKE_THEMES[1 + (npc_index % (len(SNAKE_THEMES) - 1))]
            name = f"NPC-{npc_index + 1}"
            snake = Snake(head[0], head[1], direction, theme, is_ai=True, name=name)
            snake.body = deque(body)
            self.ai_snakes.append(snake)
            occupied.update(body)
            npc_index += 1

        self.all_snakes = [self.player] + self.ai_snakes

        # 食物
        self.food = []
        for _ in range(NUM_FOOD):
            f = self.spawn_food()
            if f:
                self.food.append(f)

        self.running = True
        self.game_over = False
        self.game_over_reason = ""
        self.elapsed_time = 0.0
        self.kill_count = 0
        self.player_pressed = set()
        # NPC 孵化定时器
        self.npc_spawn_timer = 0.0

    # ---- Food helpers ----
    def occupied(self):
        occ = set()
        for snake in self.all_snakes:
            if snake.alive:
                occ.update(snake.get_body_set())
        for f in self.food:
            occ.add(f)
        return occ

    def spawn_food(self):
        occ = self.occupied()
        for _ in range(2000):
            pos = (random.randint(0, GRID_WIDTH - 1), random.randint(0, GRID_HEIGHT - 1))
            if pos not in occ:
                return pos
        return None

    def ensure_food_count(self):
        # 避免无限循环：地图太满就放弃
        attempts = 0
        while len(self.food) < NUM_FOOD and attempts < 20:
            f = self.spawn_food()
            if f:
                self.food.append(f)
            else:
                break
            attempts += 1

    # ---- AI ----
    def ai_decide(self, snake):
        if not snake.alive:
            return
        head = snake.head
        body_set = snake.get_body_set()
        own_tail = snake.body[-1]
        candidates = []

        # 阶段权重：长度越短 → 越偏吃食物快速成长；越长 → 越偏主动猎杀
        if snake.length < 5:
            food_weight, attack_weight, fear_weight = 1.8, 0.4, 1.2
        elif snake.length < 10:
            food_weight, attack_weight, fear_weight = 1.0, 1.0, 1.0
        else:
            food_weight, attack_weight, fear_weight = 0.5, 1.6, 0.6

        for d in ALL_DIRS:
            # 反向禁止
            if (d[0] == -snake.direction[0] and d[1] == -snake.direction[1]):
                continue
            nx = head[0] + d[0]
            ny = head[1] + d[1]
            # 墙
            if nx < 0 or nx >= GRID_WIDTH or ny < 0 or ny >= GRID_HEIGHT:
                continue

            # 撞其他蛇身？
            danger = False
            for other in self.all_snakes:
                if other is snake or not other.alive:
                    continue
                if (nx, ny) in other.get_body_set():
                    # 对方尾巴下一步消失则可走
                    other_list = list(other.body)
                    if (nx, ny) == other_list[-1] and not other.growing:
                        pass
                    else:
                        danger = True
                        break
            if danger:
                continue

            # 撞自己（不死，但要避开；尾巴除外）
            if (nx, ny) in body_set:
                if (nx, ny) == own_tail and not snake.growing:
                    pass
                else:
                    continue

            # 评分
            min_food_dist = 0
            if self.food:
                min_food_dist = min(abs(f[0] - nx) + abs(f[1] - ny) for f in self.food)

            straight_bonus = 2.5 if d == snake.direction else 0
            edge_penalty = 0
            if nx == 0 or nx == GRID_WIDTH - 1 or ny == 0 or ny == GRID_HEIGHT - 1:
                edge_penalty = 3

            # 远离比自己大的蛇头（求生本能）
            fear_penalty = 0
            for other in self.all_snakes:
                if other is snake or not other.alive:
                    continue
                if other.length > snake.length + 1:
                    dh = abs(other.head[0] - nx) + abs(other.head[1] - ny)
                    if dh <= 3:
                        # 长度差越大、距离越近 → 越怕
                        diff = other.length - snake.length
                        fear_penalty += (3 - dh) * diff * 0.5

            # 攻击比自己小的蛇头：靠近 → 冲过去咬
            attack_bonus = 0
            for other in self.all_snakes:
                if other is snake or not other.alive:
                    continue
                if snake.length > other.length + 1:
                    dh = abs(other.head[0] - nx) + abs(other.head[1] - ny)
                    if dh <= 5:
                        # 长度差越大、距离越近 → 越想冲
                        diff = snake.length - other.length
                        attack_bonus += (5 - dh) * diff * 0.6

            score = (-min_food_dist * 0.5 * food_weight
                     + straight_bonus
                     - edge_penalty
                     - fear_penalty * fear_weight
                     + attack_bonus * attack_weight)

            candidates.append((score, d))

        if candidates:
            candidates.sort(reverse=True)
            snake.set_direction(candidates[0][1])
        # 没路就保持当前方向（撞墙就死）

    # ---- Collision resolution ----
    def resolve_collisions(self):
        # 1) 头碰头：所有进入同一格子的蛇
        head_to_snakes = {}
        for snake in self.all_snakes:
            if not snake.alive:
                continue
            head_to_snakes.setdefault(snake.head, []).append(snake)

        head_head_killed = set()
        for pos, snakes in head_to_snakes.items():
            if len(snakes) < 2:
                continue
            snakes.sort(key=lambda s: -s.length)
            max_len = snakes[0].length
            winner = snakes[0]
            # 多条等长同时最长 → 同归于尽；否则只有短的死
            max_count = sum(1 for s in snakes if s.length == max_len)
            if max_count >= 2:
                for s in snakes:
                    head_head_killed.add(s)
                    if not s.death_reason:
                        s.death_reason = "头碰头平局"
            else:
                for s in snakes:
                    if s.length < max_len:
                        head_head_killed.add(s)
                        if not s.death_reason:
                            s.death_reason = f"被 {winner.name} 头碰头吃掉"

        # 2) 撞墙、撞身
        cut_events = []  # (attacker, victim, idx)
        for snake in self.all_snakes:
            if not snake.alive or snake in head_head_killed:
                continue
            h = snake.head

            # 撞墙
            if (h[0] < 0 or h[0] >= GRID_WIDTH or h[1] < 0 or h[1] >= GRID_HEIGHT):
                snake.death_reason = "撞墙"
                head_head_killed.add(snake)
                continue

            # 撞其他蛇身
            hit_victim = None
            hit_idx = -1
            for victim in self.all_snakes:
                if victim is snake or not victim.alive:
                    continue
                vlist = list(victim.body)
                if h in victim.get_body_set():
                    try:
                        idx = vlist.index(h)
                    except ValueError:
                        continue
                    if victim.length > snake.length:
                        # 小蛇撞大蛇身 → 小蛇死亡
                        snake.death_reason = f"撞到 {victim.name} 的身体"
                        head_head_killed.add(snake)
                        hit_victim = None
                    else:
                        # 大蛇撞小蛇身（≥ 等长）→ 截取
                        hit_victim = victim
                        hit_idx = idx
                    break  # 一个蛇只撞一个 victim

            # 撞自己身体 → 不死，无视（按需求）

            if hit_victim is not None and snake not in head_head_killed:
                cut_events.append((snake, hit_victim, hit_idx))

        # 3) 应用死亡
        for snake in head_head_killed:
            if snake.alive:
                self.kill_snake(snake)

        # 4) 应用截取
        for attacker, victim, idx in cut_events:
            if attacker.alive and victim.alive:
                self.cut_snake(attacker, victim, idx)

        # 5) 食物（step 已经处理增长，这里只移除 + 加分）
        for snake in self.all_snakes:
            if not snake.alive:
                continue
            if snake.head in self.food:
                self.food.remove(snake.head)
                snake.score += 10

        # 6) 确保食物数量
        self.ensure_food_count()

    def cut_snake(self, attacker, victim, idx):
        """
        大蛇撞小蛇身（撞到 victim 的第 idx 节）：
        - victim.body[0..idx-1] 保留（头 → 撞击点之前）
        - victim.body[idx..] 被截取作为 attacker 身体的延伸
          其中 victim.body[idx] 即 attacker 头所在位置
        - victim 被截断到 keep_part；如果全没了就死亡（body 化食物）
        """
        vlist = list(victim.body)
        keep_part = vlist[:idx]          # 头 → 撞击点之前
        cut_part = vlist[idx:]           # 撞击点 → 尾巴

        # victim 截断
        victim.body = deque(keep_part)

        if len(keep_part) == 0:
            # victim 整个被吞掉，死亡（身体化食物）
            victim.death_reason = f"被 {attacker.name} 完全吞掉"
            for pos in cut_part[1:]:
                if pos not in self.food:
                    self.food.append(pos)
            self.kill_snake(victim)
            # attacker 直接吸收 cut_part
            tail = list(attacker.body)[1:]
            new_body = [attacker.head] + cut_part[1:] + tail
            attacker.body = deque(new_body)
            # 不设 growing：下帧正常 pop 一节，让吸收的 cut_part[1:] 自然接在 body 里
        else:
            # victim 保留头部到撞击点之前，身体变短
            # attacker 吸收 cut_part[1:]（cut_part[0] 即新蛇头位置，已在 attacker.body[0]）
            tail = list(attacker.body)[1:]
            new_body = [attacker.head] + cut_part[1:] + tail
            attacker.body = deque(new_body)
            # 同上：让 step 自然 pop 一节，保持新长度

        # 攻击得分
        attacker.score += len(cut_part) * 5
        if attacker is self.player:
            self.kill_count += 1

    def kill_snake(self, snake):
        if not snake.alive:
            return
        snake.alive = False
        for pos in snake.body:
            if pos not in self.food:
                self.food.append(pos)
        if snake is self.player:
            self.game_over = True
            if not self.game_over_reason:
                self.game_over_reason = snake.death_reason or "阵亡"

    def try_spawn_npc_from_food(self):
        """
        当活 NPC 数量 < MIN_NPC_COUNT 时，食物有机会孵化成新 NPC。
        缺口越大，孵化概率越高。孵化后该食物消失，从食物位置生成一条新蛇。
        """
        alive_npc = sum(1 for s in self.ai_snakes if s.alive)
        if alive_npc >= MIN_NPC_COUNT or not self.food:
            return
        deficit = MIN_NPC_COUNT - alive_npc
        prob = min(0.85, 0.25 + deficit * 0.18)
        if random.random() > prob:
            return

        # 计算当前占用
        occupied = set()
        for s in self.all_snakes:
            if s.alive:
                occupied.update(s.get_body_set())

        # 随机选一个食物（优先选没有占用的）
        random.shuffle(self.food)
        chosen_pos = None
        for pos in self.food:
            if pos not in occupied:
                chosen_pos = pos
                break
        if chosen_pos is None:
            return

        # 找一个能放下的随机方向和长度
        direction = random.choice(ALL_DIRS)
        init_len = random.randint(*INITIAL_NPC_LEN_RANGE)
        body = [chosen_pos]
        cx, cy = chosen_pos
        dx, dy = -direction[0], -direction[1]
        for _ in range(init_len - 1):
            nx, ny = cx + dx, cy + dy
            if nx < 1 or nx >= GRID_WIDTH - 1 or ny < 1 or ny >= GRID_HEIGHT - 1:
                break
            if (nx, ny) in occupied:
                break
            body.append((nx, ny))
            cx, cy = nx, ny

        # 移除该食物
        self.food.remove(chosen_pos)

        # 创建 NPC
        theme = SNAKE_THEMES[1 + (len(self.ai_snakes) % (len(SNAKE_THEMES) - 1))]
        name = f"NPC-{len(self.ai_snakes) + 1}"
        snake = Snake(chosen_pos[0], chosen_pos[1], direction, theme, is_ai=True, name=name)
        snake.body = deque(body)
        self.ai_snakes.append(snake)
        # 同步 all_snakes
        self.all_snakes = [self.player] + self.ai_snakes

    # ---- Update ----
    def update(self, dt):
        self.elapsed_time += dt

        # 玩家速度（含加速）
        if self.player.alive and not self.game_over:
            target = BOOST_SPEED if self.player.boosting else BASE_SPEED
            t = min(1.0, SMOOTH_RATE * dt)
            self.player.current_speed += (target - self.player.current_speed) * t
            self.player.move_accumulator += self.player.current_speed * dt

        # AI 速度
        for ai in self.ai_snakes:
            if not ai.alive:
                continue
            t = min(1.0, SMOOTH_RATE * dt)
            ai.current_speed += (BASE_SPEED - ai.current_speed) * t
            ai.move_accumulator += ai.current_speed * dt

        # AI 决策（在步进之前）
        for ai in self.ai_snakes:
            if ai.alive:
                self.ai_decide(ai)

        # 步进
        food_set = set(self.food)
        for snake in self.all_snakes:
            if not snake.alive:
                continue
            steps = 0
            while snake.move_accumulator >= 1.0 and steps < MAX_STEPS_PER_FRAME:
                snake.move_accumulator -= 1.0
                steps += 1
                snake.step(food_set)
            if snake.move_accumulator >= 1.0:
                snake.move_accumulator = 0.0  # 丢掉卡顿堆积

        # 处理碰撞
        self.resolve_collisions()

        # 食物孵化 NPC：活 NPC < 阈值时，每隔一段时间从食物点生成新蛇
        self.npc_spawn_timer += dt
        if self.npc_spawn_timer >= NPC_SPAWN_CHECK_INTERVAL:
            self.npc_spawn_timer = 0.0
            self.try_spawn_npc_from_food()

    # ---- Render ----
    def cell_to_pixel(self, x, y):
        return x * CELL_SIZE, y * CELL_SIZE + GAME_OFFSET_Y

    def draw_grass(self):
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                c = (24, 40, 24) if (x + y) % 2 == 0 else (30, 52, 30)
                px, py = self.cell_to_pixel(x, y)
                pygame.draw.rect(self.screen, c, (px, py, CELL_SIZE, CELL_SIZE))

    def draw_food(self):
        for f in self.food:
            x, y = f
            px, py = self.cell_to_pixel(x, y)
            cx, cy = px + CELL_SIZE // 2, py + CELL_SIZE // 2
            pygame.draw.circle(self.screen, RED, (cx, cy), CELL_SIZE // 2 - 2)
            pygame.draw.circle(self.screen, (255, 160, 160), (cx - 3, cy - 3), 3)

    def draw_snake(self, snake):
        if not snake.alive:
            return
        for i, (x, y) in enumerate(snake.body):
            px, py = self.cell_to_pixel(x, y)
            rect = pygame.Rect(px + 1, py + 1, CELL_SIZE - 2, CELL_SIZE - 2)
            if i == 0:
                pygame.draw.rect(self.screen, snake.theme['head'], rect)
                pygame.draw.rect(self.screen, snake.theme['dark'], rect, 2)
                # 眼睛
                d = snake.direction
                cx = px + CELL_SIZE // 2
                cy = py + CELL_SIZE // 2
                ex1 = cx + d[0] * 4 - d[1] * 4
                ey1 = cy + d[1] * 4 - d[0] * 4
                ex2 = cx + d[0] * 4 + d[1] * 4
                ey2 = cy + d[1] * 4 + d[0] * 4
                pygame.draw.circle(self.screen, BLACK, (ex1, ey1), 2)
                pygame.draw.circle(self.screen, BLACK, (ex2, ey2), 2)
            else:
                pygame.draw.rect(self.screen, snake.theme['body'], rect)
                pygame.draw.circle(self.screen, snake.theme['dark'],
                                  (px + CELL_SIZE // 2, py + CELL_SIZE // 2), 2)

    def draw_hud(self):
        hud = pygame.Surface((WINDOW_WIDTH, HUD_HEIGHT))
        hud.fill((18, 22, 35))
        self.screen.blit(hud, (0, 0))
        pygame.draw.line(self.screen, (60, 80, 120), (0, HUD_HEIGHT), (WINDOW_WIDTH, HUD_HEIGHT), 2)

        # 第一行：玩家信息
        x = 14
        y = 8
        s = self.font_medium.render(self.player.theme['name'], True, self.player.theme['head'])
        self.screen.blit(s, (x, y))
        x += s.get_width() + 14

        for label, color in [
            (f"Score {self.player.score}", YELLOW),
            (f"Len {self.player.length}", WHITE),
            (f"Kills {self.kill_count}", RED),
            (f"Food {len(self.food)}", (255, 180, 100)),
        ]:
            t = self.font_small.render(label, True, color)
            self.screen.blit(t, (x, y + 4))
            x += t.get_width() + 12

        sp = self.font_small.render(
            f"Speed {self.player.current_speed:4.1f}",
            True, (255, 100, 60) if self.player.boosting else WHITE
        )
        self.screen.blit(sp, (x, y + 4))

        # 第二行：操作提示
        help_text = self.font_tiny.render(
            "↑↓←→ / WASD 移动   按住同向键加速   R 重启   Q 退出",
            True, (170, 170, 190)
        )
        self.screen.blit(help_text, (14, 48))

        # 排行榜（右上）
        all_living = sorted([s for s in self.all_snakes if s.alive], key=lambda s: -s.length)
        x_offset = WINDOW_WIDTH - 230
        y_offset = 8
        s = self.font_small.render("Leaderboard", True, WHITE)
        self.screen.blit(s, (x_offset, y_offset))
        for i, snake in enumerate(all_living[:6]):
            prefix = "▶" if snake is self.player else " "
            text = f"{prefix}{i+1}. {snake.name:<6} L:{snake.length:>2}  S:{snake.score}"
            color = snake.theme['head']
            t = self.font_tiny.render(text, True, color)
            self.screen.blit(t, (x_offset + 4, y_offset + 26 + i * 14))

    def draw_game_over(self):
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        text = self.font_huge.render("GAME OVER", True, RED)
        self.screen.blit(text, (WINDOW_WIDTH // 2 - text.get_width() // 2,
                                WINDOW_HEIGHT // 2 - 130))

        reason = self.font_large.render(f"原因: {self.game_over_reason}", True, WHITE)
        self.screen.blit(reason, (WINDOW_WIDTH // 2 - reason.get_width() // 2,
                                  WINDOW_HEIGHT // 2 - 30))

        score = self.font_large.render(f"得分 {self.player.score}    击杀 {self.kill_count}",
                                       True, YELLOW)
        self.screen.blit(score, (WINDOW_WIDTH // 2 - score.get_width() // 2,
                                 WINDOW_HEIGHT // 2 + 20))

        info = self.font_medium.render("按 R 重启   /   Q 退出", True, WHITE)
        self.screen.blit(info, (WINDOW_WIDTH // 2 - info.get_width() // 2,
                                WINDOW_HEIGHT // 2 + 80))

    def render(self):
        self.screen.fill(BLACK)
        self.draw_grass()
        self.draw_food()
        # 先画 AI，再画玩家（玩家在最上层）
        for snake in self.ai_snakes:
            self.draw_snake(snake)
        self.draw_snake(self.player)
        self.draw_hud()
        if self.game_over:
            self.draw_game_over()
        pygame.display.flip()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if self.game_over:
                    if event.key == pygame.K_r:
                        self.reset()
                    elif event.key == pygame.K_q:
                        self.running = False
                    continue
                # WASD 也支持
                if event.key in KEY_DIR_MAP:
                    self.player_pressed.add(event.key)
                    new_dir = KEY_DIR_MAP[event.key]
                    if self.player.alive:
                        self.player.set_direction(new_dir)
                elif event.key == pygame.K_r:
                    self.reset()
                elif event.key == pygame.K_q:
                    self.running = False
            elif event.type == pygame.KEYUP:
                if event.key in KEY_DIR_MAP:
                    self.player_pressed.discard(event.key)

        # boosting：当前按住的方向键里包含「与蛇头同向」的那一个
        if self.player.alive:
            self.player.boosting = any(
                KEY_DIR_MAP.get(k) == self.player.direction
                for k in self.player_pressed
                if k in KEY_DIR_MAP
            )

    async def run(self):
        while self.running:
            dt = self.clock.tick(60) / 1000.0
            self.handle_events()
            if not self.game_over:
                self.update(dt)
            self.render()
            await asyncio.sleep(0)

        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    asyncio.run(Game().run())
