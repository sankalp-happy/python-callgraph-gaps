def add(a, b):
    return a + b
def mul(a, b):
    total = 0
    for _ in range(b):
        total = add(total, a)
    return total
