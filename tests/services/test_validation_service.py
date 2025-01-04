# tests/services/test_validation_service.py
import pytest
from src.services.validation_service import ValidationService, ValidationResult
from datetime import datetime

@pytest.fixture
def validation_service():
    return ValidationService()

class TestValidationService:
    async def test_validate_action(self, validation_service):
        valid_action = {
            "type": "click",
            "target": {"selector": "#test-button"}
        }
        result = await validation_service.validate_action(valid_action)
        assert result.is_valid
        assert result.confidence > 0.8
        assert not result.errors

        invalid_action = {
            "type": "invalid_type",
            "target": {"selector": "#test-button"}
        }
        result = await validation_service.validate_action(invalid_action)
        assert not result.is_valid
        assert result.confidence < 0.5
        assert len(result.errors) > 0

    async def test_validate_email(self, validation_service):
        valid_result = await validation_service.validate_email("test@example.com")
        assert valid_result.is_valid
        assert valid_result.confidence > 0.8

        invalid_result = await validation_service.validate_email("invalid-email")
        assert not invalid_result.is_valid
        assert invalid_result.confidence < 0.5

    async def test_validate_person_name(self, validation_service):
        assert validation_service.validate_person_name("John Doe")
        assert not validation_service.validate_person_name("john")
        assert not validation_service.validate_person_name("j")

    async def test_pattern_learning(self, validation_service):
        # Train with first email
        await validation_service.validate_email("john.doe@example.com")
        
        # Test similar pattern
        result = await validation_service.validate_email("jane.doe@example.com")
        assert result.is_valid
        assert result.confidence > 0.8

    async def test_cross_validation(self, validation_service):
        email = "test@example.com"
        sources = [
            {"email": "test@example.com", "source_name": "source1"},
            {"email": "test@example.com", "source_name": "source2"},
            {"email_pattern": r"test@.*", "source_name": "source3"}
        ]
        
        result = await validation_service.cross_validate(email, sources)
        assert result.is_valid
        assert result.confidence > 0.8

    async def test_validation_metrics(self, validation_service):
        # Perform some validations
        await validation_service.validate_email("test@example.com")
        await validation_service.validate_action({"type": "click", "target": {"selector": "#test"}})
        
        metrics = validation_service.get_validation_metrics()
        assert metrics['total_validations'] > 0
        assert 'success_rate' in metrics
        assert 'pattern_cache_size' in metrics