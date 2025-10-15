# Task Completion Checklist

## Prima di Committare
1. **Linting e Formattazione**
   ```bash
   pre-commit run -a  # Esegue tutti i check
   ```
   
2. **Test Unitari**
   ```bash
   pytest  # Tutti i test devono passare
   ```

3. **Type Checking**
   ```bash
   mypy freqtrade  # Nessun errore di typing
   ```

## Per Modifiche alle Strategie
1. **Validazione Strategia**
   ```bash
   freqtrade backtesting --strategy MyStrategy --timerange 20230101-20230201
   ```

2. **Test Performance**
   - Verificare che la strategia non abbia errori di runtime
   - Controllare che i parametri siano nei range corretti
   - Validare logica di entry/exit

## Per Nuove Feature
1. **Documentazione**
   - Aggiornare docstring dei metodi
   - Aggiungere esempi se necessario
   - Documentare parametri configurabili

2. **Test Coverage**
   - Aggiungere test unitari per nuove funzionalità
   - Verificare coverage con `pytest --cov`

## Git Workflow
1. **Branch**
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feature/my-feature
   ```

2. **Commit**
   ```bash
   git add .
   git commit -m "feat: add new feature description"
   ```

3. **Push e PR**
   ```bash
   git push origin feature/my-feature
   # Creare PR verso develop branch
   ```

## Checklist Finale
- [ ] Pre-commit hooks passano
- [ ] Test unitari passano
- [ ] Type checking pulito
- [ ] Documentazione aggiornata
- [ ] Strategia testata (se applicabile)
- [ ] Commit message descrittivo
- [ ] PR verso develop branch