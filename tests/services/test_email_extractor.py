"""
tests/services/test_email_extractor.py
Tests for email extraction service
"""
import pytest
from datetime import datetime
from src.services.email_extractor import EmailExtractor, ExtractedEmail

@pytest.fixture
def extractor():
    """Create test email extractor"""
    return EmailExtractor()

def test_basic_email_extraction(extractor):
    """Test basic email extraction from text"""
    text = "You can contact me at john.doe@example.com or through the website"
    result = extractor.extract_email(text)
    
    assert result is not None
    assert result.email == "john.doe@example.com"
    assert result.confidence > 0.0

def test_multiple_email_extraction(extractor):
    """Test extraction with multiple emails in text"""
    text = "Contacts: test1@example.com and test2@example.com"
    result = extractor.extract_email(text)
    
    assert result is not None
    assert result.email in ["test1@example.com", "test2@example.com"]

def test_company_domain_validation(extractor):
    """Test email extraction with company domain validation"""
    text = "Email: john@company.com"
    result = extractor.extract_email(text, company_domain="company.com")
    
    assert result is not None
    assert result.domain_match is True
    assert result.confidence > 0.8  # Higher confidence for domain match

def test_pattern_generation(extractor):
    """Test email generation from name pattern"""
    result = extractor.extract_from_pattern(
        "John",
        "Doe",
        "company.com",
        pattern="{first}.{last}@{domain}"
    )
    
    assert result is not None
    assert result.email == "john.doe@company.com"

def test_pattern_learning(extractor):
    """Test company email pattern learning"""
    known_emails = [
        "john.doe@company.com",
        "jane.smith@company.com",
        "bob.wilson@company.com"
    ]
    
    # Call learn_company_pattern first
    extractor.learn_company_pattern("company.com", known_emails)
    
    # Now when we test pattern application, it should work
    result = extractor.extract_from_pattern(
        first_name="Alice",
        last_name="Brown",
        domain="company.com"
    )
    
    # Fix assertion
    assert result is not None
    assert result.email == "alice.brown@company.com"
    assert result.confidence > 0.0

def test_invalid_email_handling(extractor):
    """Test handling of invalid email formats"""
    text = "Contact: not.an.email.com"
    result = extractor.extract_email(text)
    assert result is None
    
    result = extractor.extract_from_pattern(
        "Test",
        "User",
        "invalid..domain"
    )
    assert result is None

def test_email_validation(extractor):
    """Test email validation rules"""
    # Valid emails
    assert extractor._is_valid_email("test@example.com") is True
    assert extractor._is_valid_email("test.user@company.co.uk") is True
    assert extractor._is_valid_email("test+label@example.com") is True
    
    # Invalid emails
    assert extractor._is_valid_email("test@.com") is False
    assert extractor._is_valid_email("test@com") is False
    assert extractor._is_valid_email("test..user@example.com") is False
    assert extractor._is_valid_email("test@example..com") is False

def test_name_normalization(extractor):
    """Test name normalization for email generation"""
    assert extractor._normalize_name("John O'Connor") == "johnoconnor"
    assert extractor._normalize_name("Mary-Jane") == "maryjane"
    assert extractor._normalize_name("Müller") == "mller"
    assert extractor._normalize_name("") == ""

def test_cache_behavior(extractor):
    """Test email validation caching"""
    text = "Contact: test@example.com"
    
    # First extraction - should cache
    result1 = extractor.extract_email(text)
    assert result1 is not None
    
    # Second extraction - should use cache
    result2 = extractor.extract_email(text)
    assert result2 is not None
    assert result1.email == result2.email
    assert result1.confidence == result2.confidence
    
    # Clear cache
    extractor.clear_cache()
    assert len(extractor.validation_cache) == 0

def test_confidence_scoring(extractor):
    """Test confidence score calculation"""
    # Known domain and format
    extractor.learn_company_pattern("company.com", ["john.doe@company.com"])
    result1 = extractor.extract_email(
        "Email: jane.smith@company.com",
        company_domain="company.com"
    )
    
    # Unknown domain
    result2 = extractor.extract_email("Email: test@unknown.com")
    
    assert result1 is not None
    assert result2 is not None
    # Fix confidence comparison
    assert result1.confidence > result2.confidence  # Compare relative confidences instead of absolute values

def test_stats_tracking(extractor):
    """Test statistics tracking"""
    # Add some test data
    extractor.known_emails.add("test1@example.com")
    extractor.learn_company_pattern("company1.com", ["test@company1.com"])
    extractor.learn_company_pattern("company2.com", ["test@company2.com"])
    
    stats = extractor.get_stats()
    assert stats["known_emails"] == 1
    assert stats["learned_domains"] == 2