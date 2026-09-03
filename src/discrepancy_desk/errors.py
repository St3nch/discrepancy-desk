"""Stable refusal categories at Desk trust seams."""


class DeskError(Exception):
    """Base class for an expected Desk refusal."""


class ConfigurationError(DeskError):
    """Required configuration is absent or unsafe."""


class MigrationDriftError(DeskError):
    """An applied migration no longer matches its recorded digest."""


class VaultIntegrityError(DeskError):
    """Vault bytes do not match their content address."""


class EvidenceContractError(DeskError):
    """Evidence does not satisfy the declared Locator/Excerpt contract."""


class RecordNotFoundError(DeskError):
    """A requested durable Record object does not exist."""


class DecisionAuthorityError(DeskError):
    """The human-Decision capability is absent."""
