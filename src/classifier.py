import abc
import math
import pickle
import copy
import cv2
import numpy as np
import detector


def minibatches(X, y, batchsize, shuffle=True):
    assert X.shape[0] == y.shape[0]
    indices = np.arange(X.shape[0])
    if shuffle:
        np.random.shuffle(indices)

    for i in range(0, X.shape[0], batchsize):
        excerpt = indices[i:i + batchsize]
        yield X[excerpt], y[excerpt]


class Classifier:

    def predict(self, X):
        return NotImplemented


try:
    from sklearn.base import BaseEstimator
except:
    BaseEstimator = Classifier


class MLClassifier(BaseEstimator):

    def fit(self, X, y):
        return NotImplemented

    def predict(self, X):
        return NotImplemented

    def score(self, X, y):
        return np.sum(self.predict(X) != y) / len(y)

    def save(self, path):
        with open(path, 'wb') as f:
            pickle.dump(self.__dict__, f)

    def load(self, path):
        with open(path, 'rb') as f:
            self.__dict__.update(pickle.load(f))


class SimpleHSVRedClassifier(Classifier):

    def __init__(self, lower_red=170, upper_red=10):
        self._lower_red = lower_red
        self._upper_red = upper_red

    def predict(self, X):
        mask = cv2.inRange(X, np.array([self._lower_red, 30, 30]), np.array([180, 255, 255])) \
            + cv2.inRange(X, np.array([0, 30, 30]), np.array([self._upper_red, 255, 255]))
        return mask


class LogisticRegression(MLClassifier):

    def __init__(self,
                 learning_rate=0.01,
                 max_iter=1000,
                 batchsize=None,
                 tol=1e-4):
        self.learning_rate = learning_rate
        self.max_iter = max_iter
        self.batchsize = batchsize
        self.tol = tol

    def sigmoid(self, z):
        return 1.0 / (1.0 + np.exp(-z))

    def fit(self, X, y):
        assert len(np.unique(y)) == 2, str(np.unique(y))
        batchsize = self.batchsize if self.batchsize is not None else X.shape[0]
        n_dims = X.shape[1]

        self.w = np.random.randn(1, n_dims) / n_dims
        for _ in range(self.max_iter):
            w_prev = self.w
            for Xb, yb in minibatches(X, y, batchsize, shuffle=True):
                h = self.sigmoid(Xb @ self.w.T)
                self.w = self.w - self.learning_rate * (
                    Xb.T @ (h - yb.reshape(-1, 1))).T
            if np.linalg.norm(w_prev - self.w) < self.tol:
                break

    def predict(self, X):
        return (X @ self.w.T >= 0).astype(int).reshape(-1)


class OneVsAllLogisticRegression(MLClassifier):

    def __init__(self,
                 learning_rate=0.01,
                 max_iter=1000,
                 batchsize=None,
                 tol=1e-4):
        self.learning_rate = learning_rate
        self.max_iter = max_iter
        self.batchsize = batchsize
        self.tol = tol

    def sigmoid(self, z):
        return 1.0 / (1.0 + np.exp(-z))

    def fit(self, X, y):
        assert np.min(y) == 0 and len(np.unique(y)) - 1 == np.max(y)
        batchsize = self.batchsize if self.batchsize is not None else X.shape[0]
        n_data = X.shape[0]
        n_dims = X.shape[1]
        n_classes = len(np.unique(y))

        self.n_dims = n_dims
        self.n_classes = n_classes

        self.w = np.zeros((n_classes, 1, n_dims))
        for k in range(n_classes):
            wk = np.random.randn(1, n_dims) / n_dims
            yk = (y == k).astype(int).reshape(-1, 1)
            for _ in range(self.max_iter):
                wk_prev = wk
                for Xb, yb in minibatches(X, yk, batchsize, shuffle=True):
                    h = self.sigmoid(Xb @ wk.T)
                    wk = wk - self.learning_rate * (Xb.T @ (h - yb)).T
                if np.linalg.norm(wk_prev - wk) < self.tol:
                    break

            self.w[k] = wk

    def predict(self, X):
        return np.argmax(np.hstack(
            [X @ self.w[k].T for k in range(self.n_classes)]),
                         axis=1).astype(int).reshape(-1)


class KaryLogisticRegression(MLClassifier):

    def __init__(self,
                 learning_rate=0.01,
                 max_iter=1000,
                 batchsize=None,
                 tol=1e-4):
        self.learning_rate = learning_rate
        self.max_iter = max_iter
        self.batchsize = batchsize
        self.tol = tol

    def softmax(self, z):
        e_z = np.exp(z - np.max(z, axis=1, keepdims=True))
        return e_z / e_z.sum(axis=1, keepdims=True)

    def fit(self, X, y):
        assert np.min(y) == 0 and len(np.unique(y)) - 1 == np.max(y)
        batchsize = self.batchsize if self.batchsize is not None else X.shape[0]
        n_dims = X.shape[1]
        n_classes = len(np.unique(y))
        e = np.eye(n_classes)

        self.w = np.random.randn(n_classes, n_dims) / n_dims
        for _ in range(self.max_iter):
            w_prev = self.w
            for Xb, yb in minibatches(X, y, batchsize, shuffle=True):
                self.w = self.w + self.learning_rate * (
                    (e[yb, :] - self.softmax(Xb @ self.w.T)).T @ Xb)
            if np.linalg.norm(w_prev - self.w) < self.tol:
                break

    def predict(self, X):
        return np.argmax(X @ self.w.T, axis=1).astype(int).reshape(-1)


class GaussianNaiveBayes(MLClassifier):
    _LOG_2PI = np.log(2 * math.pi)

    def __init__(self):
        pass

    def log_multivariate_normal_pdf(self, x, avg, cov):
        dim = self.n_dims
        dev = x - avg
        maha = np.sum((dev @ np.linalg.pinv(cov)) * dev, axis=1)
        return -0.5 * (dim * GaussianNaiveBayes._LOG_2PI +
                       np.log(np.linalg.det(cov)) + maha)

    def fit(self, X, y):
        assert np.min(y) == 0 and len(np.unique(y)) - 1 == np.max(y), str(
            np.unique(y)) + str(X.shape)
        n_data = X.shape[0]
        n_dims = X.shape[1]
        n_classes = len(np.unique(y))
        self.n_dims = n_dims
        self.n_classes = n_classes

        self.w = np.zeros((n_classes))
        self.avg = np.zeros((n_classes, 1, n_dims))
        self.cov = np.zeros((n_classes, n_dims, n_dims))

        for k in range(n_classes):
            Xk = X[y == k, :]
            n_data_k = Xk.shape[0]

            self.w[k] = n_data_k / n_data
            self.avg[k, :, :] = np.mean(Xk, axis=0, keepdims=True)
            self.cov[k, :, :] = np.cov(Xk.T)

    def predict(self, X):
        return np.argmax(np.array([
            np.log(self.w[k]) + self.log_multivariate_normal_pdf(X, self.avg[k], self.cov[k]) \
            for k in range(self.n_classes)
        ]), axis=0)


class EigenFaceClassifier(MLClassifier):

    def __init__(self, epsilon=0.01):
        self.epsilon = epsilon

    def fit(self, X):
        self._n_trainX = X.shape[0]
        self._trainX = X.reshape(self._n_trainX, -1).T
        self._trainX_mean = np.mean(self._trainX, axis=1).reshape(-1, 1)

        self._compute_principle_components()

    def _compute_principle_components(self):
        A = self._trainX - self._trainX_mean
        u, s, vh = np.linalg.svd(A, full_matrices=False)
        self.principle_components = u
        self.singular_values = s**2

    def predict(self, X, n_pcs=None, return_distance=False):
        # Eigenface recognition: https://en.wikipedia.org/wiki/Eigenface#Use_in_facial_recognition
        rX = self.construct(X, n_pcs=n_pcs)
        distance = np.sum((X - rX)**2, axis=1)
        if return_distance:
            return distance < self.epsilon, distance
        else:
            return distance < self.epsilon

    def construct(self, X, n_pcs=None):
        if n_pcs == None:
            n_pcs = self.principle_components.shape[-1]

        X = X.T
        X = X - self._trainX_mean

        u = self.principle_components[:, :n_pcs]
        w = u.T @ X
        recon = u @ w + self._trainX_mean
        return recon.T


class SSBBoxDeterministic(Classifier):

    def __init__(self, image_area):
        self._image_area = image_area

    def predict(self, region):
        return self._predict_region(region)

    def _predict_region(self, region):
        minr, minc, maxr, maxc = region.bbox
        lr = maxr - minr
        lc = maxc - minc

        if max(lc, lr) - min(lc, lr) > 1.5 * min(lc, lr):
            return False

        region_cvx_img = np.pad(region.convex_image,
                                10,
                                'constant',
                                constant_values=0)
        for contour in detector.Contour.find(region_cvx_img):
            if contour.area > self._image_area * 0.001 and contour.area > region.bbox_area * 0.2:
                # if not (region.image[region.image != 0].sum() >
                #         contour.area * 0.4):
                #     return False

                approx_polygon = contour.approx_polygon()
                n_edges = approx_polygon.n_edges

                if 7 <= n_edges <= 10:
                    degs = approx_polygon.angles_deg * 2
                    continuous_degs_sums = [
                        sum(degs[i:i + 4]) for i in range(n_edges)
                    ]

                    n_valid_partial_octagon = sum([
                        160 < v % 360 < 200 or 160 < (v + 180) % 360 < 200
                        for v in continuous_degs_sums
                    ])
                    if n_valid_partial_octagon >= 2:
                        return True
        return False
