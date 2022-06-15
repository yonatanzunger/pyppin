import matplotlib.pyplot as plt

from pyppin.threading.rate_limiter import RateLimiter

RATE = 10000
DURATION = 2.0

throttle = RateLimiter()
times: list[float] = []
expected: list[float] = []

print(f'Timing {DURATION * RATE} intervals at {RATE} qps')
throttle.set_rate(RATE)
times.extend([throttle.wait() for i in range(int(DURATION * RATE))])

offset = [times[i + 1] - times[0] for i in range(len(times) - 1)]
intervals = [times[i + 1] - times[i] for i in range(len(times) - 1)]
ratio = [interval * RATE for interval in intervals]
rates = [1.0 / interval for interval in intervals]

fig, ax = plt.subplots()
# ax.scatter(offset, rates)
ax.scatter(offset, ratio)
plt.show()

# NOTE: Adjusting the fudge factor seems to have no effect here. WTF is going on?
# We seem to be steadily seeing ratios of 1.14-1.25
