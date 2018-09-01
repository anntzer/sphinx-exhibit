"""
Custom capture example
======================
"""

from matplotlib import pyplot as plt

fig, ax = plt.subplots()
ax.plot([1, 2])
fig.savefig("test.png")
plt.close("all")

"""
.. exhibit-capture:: test.png foo
"""
