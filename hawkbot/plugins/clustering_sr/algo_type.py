from enum import Enum

from hawkbot.plugins.clustering_sr.algos.bmeans_algo import BMeansAlgo
from hawkbot.plugins.clustering_sr.algos.custom_algo import CustomAlgo
from hawkbot.plugins.clustering_sr.algos.dmeans_algo import DMeansAlgo
from hawkbot.plugins.clustering_sr.algos.immediate_linear_algo import ImmediateLinearAlgo
from hawkbot.plugins.clustering_sr.algos.kmeans_algo import KMeansAlgo
from hawkbot.plugins.clustering_sr.algos.lin_algo import LinAlgo
from hawkbot.plugins.clustering_sr.algos.lin_linear_peaks_troughs_highlow_algo import LinLinearPeaksTroughsHighLowAlgo
from hawkbot.plugins.clustering_sr.algos.lin_peakstroughs_highlow_algo import LinPeaksTroughsHighLowAlgo
from hawkbot.plugins.clustering_sr.algos.linear_algo import LinearAlgo
from hawkbot.plugins.clustering_sr.algos.log_algo import LogAlgo
from hawkbot.plugins.clustering_sr.algos.peakstroughs_algo import PeaksTroughsAlgo
from hawkbot.plugins.clustering_sr.algos.peakstroughs_highlow_algo import PeaksTroughsHighLowAlgo


class AlgoType(Enum):
    IMMEDIATE_LINEAR = 'IMMEDIATE_LINEAR', ImmediateLinearAlgo
    LINEAR = 'LINEAR', LinearAlgo
    LIN = 'LIN', LinAlgo
    LOG = 'LOG', LogAlgo
    PEAKS_TROUGHS = 'PEAKS_TROUGHS', PeaksTroughsAlgo
    PEAKS_TROUGHS_HIGHLOW = 'PEAKS_TROUGHS_HIGHLOW', PeaksTroughsHighLowAlgo
    KMEANS = 'KMEANS', KMeansAlgo
    BMEANS = 'BMEANS', BMeansAlgo
    DMEANS = 'DMEANS', DMeansAlgo
    LIN_PEAKS_TROUGHS_HIGHLOW = 'LIN_PEAKS_TROUGHS_HIGHLOW', LinPeaksTroughsHighLowAlgo
    LIN_LINEAR_PEAKS_TROUGHS_HIGHLOW = 'LIN_LINEAR_PEAKS_TROUGHS_HIGHLOW', LinLinearPeaksTroughsHighLowAlgo
    CUSTOM = 'CUSTOM', CustomAlgo
