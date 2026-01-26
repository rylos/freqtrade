import math

# Formula attuale
def current_reward(trade_count):
    if trade_count <= 0:
        return 0
    return math.log(1 + trade_count / 100) / 10

# Formula proposta: più aggressiva da 300+
def new_reward(trade_count):
    if trade_count <= 0:
        return 0
    # Soglia a 300, poi crescita più rapida
    if trade_count >= 300:
        base = math.log(1 + 300 / 100) / 10  # Reward a 300
        excess = trade_count - 300
        # Crescita lineare oltre 300 (0.05% per trade)
        bonus = (excess / 100) * 0.05
        return base + bonus
    else:
        return math.log(1 + trade_count / 100) / 10

print('Trade Count | Current | New    | Diff')
print('------------|---------|--------|-------')
for count in [100, 200, 300, 400, 500, 600, 800, 1000]:
    curr = current_reward(count) * 100
    new = new_reward(count) * 100
    diff = new - curr
    print(f'{count:10d}  | {curr:6.1f}% | {new:6.1f}% | +{diff:5.1f}%')
