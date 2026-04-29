# compliance-closing-simulator

Closes the regtech loop: reads pending IOC fraud cases, groups them by RUT when applicable, queries the regtech-rag-chile predictor for legal deadlines, and emits a prioritized payment queue consumed by deadline-chaser.
