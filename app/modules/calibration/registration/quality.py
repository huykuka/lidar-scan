"""
Quality evaluation for registration results.
"""
from dataclasses import dataclass
from typing import Tuple


@dataclass
class QualityMetrics:
    """Metrics for evaluating registration quality"""
    fitness: float
    rmse: float
    quality: str  # "excellent", "good", "poor"


class QualityEvaluator:
    """
    Evaluates the quality of point cloud registration results.
    
    Quality is based on:
    - Fitness: ratio of overlapping points (0.0-1.0)
    - RMSE: root mean square error of inlier correspondences (meters)
    """
    
    def __init__(self, min_fitness: float = 0.7, max_rmse: float = 0.05):
        """
        Initialize quality evaluator.
        
        Args:
            min_fitness: Minimum fitness for "good" quality (default: 0.7)
            max_rmse: Maximum RMSE for "good" quality in meters (default: 0.05)
        """
        self.min_fitness = min_fitness
        self.max_rmse = max_rmse
    
    def evaluate(self, fitness: float, rmse: float) -> QualityMetrics:
        """
        Evaluate registration quality.
        
        Args:
            fitness: Fitness score from registration (0.0-1.0)
            rmse: RMSE in meters
            
        Returns:
            QualityMetrics with quality classification
        """
        quality = self._classify_quality(fitness, rmse)
        
        return QualityMetrics(
            fitness=fitness,
            rmse=rmse,
            quality=quality
        )
    
    def _classify_quality(self, fitness: float, rmse: float) -> str:
        """
        Classify registration quality based on fitness and RMSE.
        
        Args:
            fitness: Fitness score (0.0-1.0)
            rmse: RMSE in meters
            
        Returns:
            Quality classification: "excellent", "good", or "poor"
        """
        if fitness >= 0.9 and rmse <= 0.02:
            return "excellent"
        elif fitness >= self.min_fitness and rmse <= self.max_rmse:
            return "good"
        else:
            return "poor"
    
    def is_acceptable(self, fitness: float, rmse: float) -> bool:
        """
        Check if registration result meets minimum quality thresholds.
        
        Args:
            fitness: Fitness score
            rmse: RMSE in meters
            
        Returns:
            True if quality is acceptable (good or excellent)
        """
        quality = self._classify_quality(fitness, rmse)
        return quality in ["excellent", "good"]
