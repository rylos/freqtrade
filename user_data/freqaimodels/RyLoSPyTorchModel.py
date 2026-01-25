"""
RyLoS PyTorch Model - MLP Regressor per predire ritorno futuro
Basato su PyTorchMLPRegressor di FreqAI
"""
import logging
from typing import Any

import torch

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
    Modello PyTorch MLP per regression sul ritorno futuro
    
    Predice il ritorno percentuale a 12 candele (1 ora su timeframe 5m).
    Usato come filtro ML per entry nella strategia RyLoS.
    
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
        Training del modello MLP
        
        Args:
            data_dictionary: Dict con train_features, train_labels, ecc.
            dk: DataKitchen object per la pair corrente
            
        Returns:
            PyTorchModelTrainer: Trainer con modello trainato
        """
        n_features = data_dictionary["train_features"].shape[-1]
        
        # Crea modello MLP
        model = PyTorchMLPModel(
            input_dim=n_features,
            output_dim=1,  # Regression: 1 output (ritorno %)
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
        
        logger.info(f"Training completato per {dk.pair}")
        
        return trainer
