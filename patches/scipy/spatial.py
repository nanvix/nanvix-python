"""Nanvix scipy.spatial stub."""


class distance:
    @staticmethod
    def euclidean(u, v):
        return sum((a - b) ** 2 for a, b in zip(u, v)) ** 0.5

    @staticmethod
    def cosine(u, v):
        return 0.0

    @staticmethod
    def cdist(XA, XB, metric='euclidean'):
        return [[0.0]]
