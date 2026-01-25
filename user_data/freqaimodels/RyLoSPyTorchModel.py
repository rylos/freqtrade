"""
RyLoS PyTorch Model - MLP Regressor per predire ritorno futuro
Basato su PyTorchMLPRegressor di FreqAI
"""
import logging
from typing import Any

import torch
from pandas import DataFrame

from freqtrade.freqai.base_models.BasePyTorchRegressor import BasePyTorchRegressor
from freqtrade.freqai.data_kitchen import FreqaiDataKitchen
from freqtrade.freqai.torch.PyTorchDataConvertor import (
    DefaultPyTorchDataConvertor,
    PyTorchDataConvertor,
)
from freqtrade.freqai.torch.PyTorchMLPModel import PyTorchMLPModel
from freqtrade.freqai.torch.PyTorchModelTrainer import PyTorchModelTrainer


logger = logging.getLogger(__name__)


class RyLoSPyTorchModel(BasePyTorchRegressor):
    """
    Modello PyTorch MLP per regression multi-horizon
    
    Supporta sia single-target che multi-target:
    - Single-target: Predice ritorno a 1 ora (&-s_close)
    - Multi-target: Predice ritorni a 15m, 30m, 1h (&-s_close_15m, &-s_close_30m, &-s_close_1h)
    
    Il numero di output viene rilevato automaticamente dal numero di target columns.
    
    Configurazione in config.json:
    {
        "freqai": {
            "model_training_parameters": {
                "learning_rate": 0.001,
                "trainer_kwargs": {
                    "n_epochs": 50,
                    "batch_size": 1024
                },
                "model_kwargs": {
                    "hidden_dim": 128,
                    "dropout_percent": 0.2,
                    "n_layer": 3
                }
            }
        }
    }
    """

    @property
    def data_convertor(self) -> PyTorchDataConvertor:
        """Data convertor per regression (target = float)"""
        return DefaultPyTorchDataConvertor(target_tensor_type=torch.float)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        config = self.freqai_info.get("model_training_parameters", {})
        self.learning_rate: float = config.get("learning_rate", 3e-4)
        self.model_kwargs: dict[str, Any] = config.get("model_kwargs", {})
        self.trainer_kwargs: dict[str, Any] = config.get("trainer_kwargs", {})

    def fit(self, data_dictionary: dict, dk: FreqaiDataKitchen, **kwargs) -> Any:
        """
        Training del modello MLP con supporto multi-target
        
        Supporta sia single-target (1 output) che multi-target (3 outputs per 15m, 30m, 1h).
        Il numero di output viene rilevato automaticamente dal numero di colonne target.
        
        Args:
            data_dictionary: Dict con train_features, train_labels, ecc.
            dk: DataKitchen object per la pair corrente
            
        Returns:
            PyTorchModelTrainer: Trainer con modello trainato
        """
        n_features = data_dictionary["train_features"].shape[-1]
        
        # Detect number of targets (single or multi-target)
        n_targets = data_dictionary["train_labels"].shape[-1]
        
        logger.info(
            f"{dk.pair}: Training model with {n_features} features and {n_targets} target(s)"
        )
        
        # Crea modello MLP con output_dim dinamico
        model = PyTorchMLPModel(
            input_dim=n_features,
            output_dim=n_targets,  # Dinamico: 1 per single-target, 3 per multi-horizon
            **self.model_kwargs
        )
        model.to(self.device)
        
        # Optimizer e loss function
        optimizer = torch.optim.AdamW(model.parameters(), lr=self.learning_rate)
        criterion = torch.nn.MSELoss()
        
        # Check continual learning
        trainer = self.get_init_model(dk.pair)
        if trainer is None:
            trainer = PyTorchModelTrainer(
                model=model,
                optimizer=optimizer,
                criterion=criterion,
                device=self.device,
                data_convertor=self.data_convertor,
                tb_logger=self.tb_logger,
                **self.trainer_kwargs,
            )
        
        # Training
        trainer.fit(data_dictionary, self.splits)
        
        logger.info(
            f"{dk.pair}: Training completato - "
            f"{n_features} features, {n_targets} target(s)"
        )
        
        return trainer

    def predict(
        self, unfiltered_df: DataFrame, dk: FreqaiDataKitchen, **kwargs
    ) -> tuple[DataFrame, dict]:
        """
        Custom predict method with multi-target support
        
        Overrides BasePyTorchRegressor.predict() to handle multiple output columns.
        Uses the same feature pipeline as the parent class to ensure consistency.
        
        Args:
            unfiltered_df: Full dataframe for the current pair
            dk: DataKitchen object with label_list and feature_pipeline
            
        Returns:
            tuple: (pred_df, do_preds) where pred_df has columns for each target
        """
        # Filter features using the same approach as parent class
        filtered_df, _ = dk.filter_features(
            unfiltered_df, dk.training_features_list, training_filter=False
        )
        dk.data_dictionary["prediction_features"] = filtered_df

        # Apply feature pipeline (includes VarianceThreshold, SVM outlier removal, etc.)
        dk.data_dictionary["prediction_features"], outliers, _ = dk.feature_pipeline.transform(
            dk.data_dictionary["prediction_features"], outlier_check=True
        )

        # Convert to tensor
        x = self.data_convertor.convert_x(
            dk.data_dictionary["prediction_features"], device=self.device
        )
        
        # Get model and make predictions
        self.model.model.eval()
        with torch.no_grad():
            y = self.model.model(x)
        
        # Convert predictions to DataFrame with ALL target columns (multi-target support)
        pred_df = DataFrame(y.detach().cpu().tolist(), columns=dk.label_list)
        
        # Apply inverse transform to predictions
        pred_df, _, _ = dk.label_pipeline.inverse_transform(pred_df)
        
        # Set DI values and do_predict mask
        if dk.feature_pipeline["di"]:
            dk.DI_values = dk.feature_pipeline["di"].di_values
        else:
            import numpy as np
            dk.DI_values = np.zeros(outliers.shape[0])
        dk.do_predict = outliers
        
        logger.info(
            f"{dk.pair}: Predictions generated - "
            f"{len(dk.label_list)} target(s): {dk.label_list}"
        )
        
        return (pred_df, dk.do_predict)
