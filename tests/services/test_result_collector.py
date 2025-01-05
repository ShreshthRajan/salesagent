"""
tests/services/test_result_collector.py
Tests for result collection service
"""
import pytest
import asyncio
from datetime import datetime
import tempfile
from pathlib import Path
import shutil

from src.services.result_collector import ResultCollector, SearchResult

@pytest.fixture
def temp_storage():
    """Create temporary storage directory"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)

@pytest.fixture
def collector(temp_storage):
    """Create test result collector"""
    return ResultCollector(storage_dir=temp_storage)

@pytest.fixture
def sample_result():
    """Create sample search result"""
    return SearchResult(
        company_name="Test Company",
        person_name="John Doe",
        title="CEO",
        email="john@testcompany.com",
        confidence=0.9,
        source="apollo"
    )

@pytest.mark.asyncio
async def test_add_result(collector, sample_result):
    """Test adding new result"""
    # Add result
    success = await collector.add_result(sample_result)
    assert success is True
    
    # Verify result was added
    key = collector._generate_result_key(sample_result)
    stored_result = collector.get_result(key)
    assert stored_result is not None
    assert stored_result.person_name == "John Doe"
    assert stored_result.email == "john@testcompany.com"

@pytest.mark.asyncio
async def test_duplicate_handling(collector, sample_result):
    """Test handling of duplicate results"""
    # Add initial result
    await collector.add_result(sample_result)
    
    # Create duplicate with lower confidence
    duplicate = SearchResult(
        company_name="Test Company",
        person_name="John Doe",
        title="CEO",
        email="john@testcompany.com",
        confidence=0.8,
        source="apollo"
    )
    
    # Add duplicate
    success = await collector.add_result(duplicate)
    assert success is False  # Should not update existing result
    
    # Create duplicate with higher confidence
    better_result = SearchResult(
        company_name="Test Company",
        person_name="John Doe",
        title="CEO",
        email="john.doe@testcompany.com",  # Better email
        confidence=0.95,
        source="apollo"
    )
    
    # Add better result
    success = await collector.add_result(better_result)
    assert success is True  # Should update existing result
    
    # Verify updated result
    key = collector._generate_result_key(sample_result)
    stored_result = collector.get_result(key)
    assert stored_result.confidence == 0.95
    assert stored_result.email == "john.doe@testcompany.com"

@pytest.mark.asyncio
async def test_batch_results(collector):
    """Test adding multiple results in batch"""
    results = [
        SearchResult(
            company_name="Company A",
            person_name="Person A",
            title="CEO",
            email="a@company.com",
            confidence=0.9,
            source="apollo"
        ),
        SearchResult(
            company_name="Company B",
            person_name="Person B",
            title="CFO",
            email="b@company.com",
            confidence=0.8,
            source="apollo"
        )
    ]
    
    status = await collector.add_batch_results(results)
    assert len(status) == 2
    assert all(status.values())  # All should succeed
    
    # Verify both results were added
    company_a_results = collector.get_company_results("Company A")
    company_b_results = collector.get_company_results("Company B")
    assert len(company_a_results) == 1
    assert len(company_b_results) == 1

@pytest.mark.asyncio
async def test_result_persistence(temp_storage):
    """Test result persistence across collector instances"""
    # Create first collector and add result
    collector1 = ResultCollector(storage_dir=temp_storage)
    result = SearchResult(
        company_name="Test Company",
        person_name="John Doe",
        title="CEO",
        email="john@test.com",
        confidence=0.9,
        source="apollo"
    )
    await collector1.add_result(result)
    
    # Create new collector instance and verify result loads
    collector2 = ResultCollector(storage_dir=temp_storage)
    loaded_results = collector2.get_company_results("Test Company")
    assert len(loaded_results) == 1
    assert loaded_results[0].email == "john@test.com"

@pytest.mark.asyncio
async def test_result_update(collector, sample_result):
    """Test updating existing result"""
    # Add initial result
    await collector.add_result(sample_result)
    key = collector._generate_result_key(sample_result)
    
    # Update result
    updates = {
        "email": "updated@test.com",
        "confidence": 0.95,
        "metadata": {"verified": True}
    }
    
    success = await collector.update_result(key, updates)
    assert success is True
    
    # Verify updates
    updated = collector.get_result(key)
    assert updated.email == "updated@test.com"
    assert updated.confidence == 0.95
    assert updated.metadata.get("verified") is True

@pytest.mark.asyncio
async def test_result_removal(collector, sample_result):
    """Test removing result"""
    # Add result
    await collector.add_result(sample_result)
    key = collector._generate_result_key(sample_result)
    
    # Remove result
    success = await collector.remove_result(key)
    assert success is True
    
    # Verify removal
    assert collector.get_result(key) is None
    assert len(collector.get_company_results(sample_result.company_name)) == 0

def test_statistics(collector, sample_result):
    """Test statistics calculation"""
    asyncio.run(collector.add_result(sample_result))
    
    stats = collector.get_stats()
    assert stats["total_results"] == 1
    assert stats["total_companies"] == 1
    assert stats["results_with_email"] == 1
    assert stats["average_confidence"] == 0.9
    assert stats["storage_size_mb"] > 0

def test_result_key_generation(collector):
    """Test result key generation"""
    result = SearchResult(
        company_name="Test Company, Inc.",
        person_name="John Q. Doe",
        title="CEO",
        email="john@test.com",
        confidence=0.9,
        source="apollo"
    )
    
    key = collector._generate_result_key(result)
    # Update expected key format
    expected_key = "test_company_inc_john_q_doe"
    assert key == expected_key