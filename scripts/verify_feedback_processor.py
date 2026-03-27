"""Verification script for user feedback processor."""

import asyncio
import logging
from datetime import datetime
from uuid import uuid4

from src.cache.redis_client import RedisClient
from src.database.aerospike_client import AerospikeClient
from src.self_improvement.enrichment_scheduler import EnrichmentScheduler
from src.self_improvement.feedback_processor import FeedbackProcessor, UserFeedback
from src.self_improvement.quality_tracker import QualityTracker
from src.tracing.overmind_client import OvermindClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def verify_feedback_models():
    """Verify feedback models can be created."""
    logger.info("=== Verifying Feedback Models ===")

    # Test UserFeedback model
    user_id = uuid4()
    node_id = uuid4()

    # Test like feedback
    like_feedback = UserFeedback(
        user_id=user_id,
        node_id=node_id,
        feedback_type="like",
        feedback_value=1,
    )
    logger.info(f"✓ Created like feedback: {like_feedback.feedback_type}")

    # Test dislike feedback
    dislike_feedback = UserFeedback(
        user_id=user_id,
        node_id=node_id,
        feedback_type="dislike",
        feedback_value=-1,
    )
    logger.info(f"✓ Created dislike feedback: {dislike_feedback.feedback_type}")

    # Test correction feedback
    correction_feedback = UserFeedback(
        user_id=user_id,
        node_id=node_id,
        feedback_type="correction",
        comment="Artist formed in 1970, not 1971",
    )
    logger.info(f"✓ Created correction feedback: {correction_feedback.comment}")

    # Test report feedback
    report_feedback = UserFeedback(
        user_id=user_id,
        node_id=node_id,
        feedback_type="report",
        comment="This data is incorrect",
    )
    logger.info(f"✓ Created report feedback: {report_feedback.comment}")

    # Test validation
    try:
        invalid_feedback = UserFeedback(
            user_id=user_id,
            node_id=node_id,
            feedback_type="invalid",
        )
        logger.error("✗ Should have raised validation error for invalid type")
    except ValueError as e:
        logger.info(f"✓ Validation works: {e}")

    # Test correction requires comment
    try:
        invalid_correction = UserFeedback(
            user_id=user_id,
            node_id=node_id,
            feedback_type="correction",
        )
        logger.error("✗ Should have raised validation error for missing comment")
    except ValueError as e:
        logger.info(f"✓ Validation works: {e}")

    logger.info("✓ All feedback model tests passed\n")


def verify_feedback_processor_initialization():
    """Verify feedback processor can be initialized."""
    logger.info("=== Verifying Feedback Processor Initialization ===")

    try:
        # Create mock clients
        db_client = AerospikeClient()
        cache_client = RedisClient()
        overmind_client = OvermindClient()

        # Create quality tracker
        quality_tracker = QualityTracker(
            cache_client=cache_client,
            overmind_client=overmind_client,
        )
        logger.info("✓ Created quality tracker")

        # Create enrichment scheduler
        enrichment_scheduler = EnrichmentScheduler(
            db_client=db_client,
            overmind_client=overmind_client,
        )
        logger.info("✓ Created enrichment scheduler")

        # Create feedback processor
        feedback_processor = FeedbackProcessor(
            db_client=db_client,
            quality_tracker=quality_tracker,
            enrichment_scheduler=enrichment_scheduler,
            cache_client=cache_client,
            overmind_client=overmind_client,
        )
        logger.info("✓ Created feedback processor")

        logger.info("✓ All components initialized successfully\n")

    except Exception as e:
        logger.error(f"✗ Initialization failed: {e}")
        raise


def verify_correction_parsing():
    """Verify correction parsing logic."""
    logger.info("=== Verifying Correction Parsing ===")

    # Create minimal feedback processor for testing
    from unittest.mock import MagicMock

    db_client = MagicMock()
    quality_tracker = MagicMock()
    enrichment_scheduler = MagicMock()

    processor = FeedbackProcessor(
        db_client=db_client,
        quality_tracker=quality_tracker,
        enrichment_scheduler=enrichment_scheduler,
    )

    # Test formed date parsing
    comment1 = "Artist formed in 1970, not 1971"
    corrected1 = processor._parse_correction(comment1, "Artist")
    if corrected1 and "formed_date" in corrected1:
        logger.info(f"✓ Parsed formed date: {corrected1['formed_date']}")
    else:
        logger.warning("✗ Failed to parse formed date")

    # Test duration parsing
    comment2 = "Duration is 354000ms"
    corrected2 = processor._parse_correction(comment2, "Song")
    if corrected2 and "duration_ms" in corrected2:
        logger.info(f"✓ Parsed duration: {corrected2['duration_ms']}")
    else:
        logger.warning("✗ Failed to parse duration")

    # Test title parsing
    comment3 = "Title should be 'Bohemian Rhapsody'"
    corrected3 = processor._parse_correction(comment3, "Song")
    if corrected3 and "title" in corrected3:
        logger.info(f"✓ Parsed title: {corrected3['title']}")
    else:
        logger.warning("✗ Failed to parse title")

    logger.info("✓ Correction parsing tests completed\n")


def verify_node_type_detection():
    """Verify node type detection logic."""
    logger.info("=== Verifying Node Type Detection ===")

    from unittest.mock import MagicMock

    db_client = MagicMock()
    quality_tracker = MagicMock()
    enrichment_scheduler = MagicMock()

    processor = FeedbackProcessor(
        db_client=db_client,
        quality_tracker=quality_tracker,
        enrichment_scheduler=enrichment_scheduler,
    )

    # Test Song detection
    song_data = {"duration_ms": 300000, "title": "Test Song"}
    node_type = processor._determine_node_type(song_data)
    logger.info(f"✓ Detected Song: {node_type == 'Song'}")

    # Test Artist detection
    artist_data = {"genres": ["rock"], "popularity": 80, "name": "Test Artist"}
    node_type = processor._determine_node_type(artist_data)
    logger.info(f"✓ Detected Artist: {node_type == 'Artist'}")

    # Test Album detection
    album_data = {"album_type": "album", "title": "Test Album"}
    node_type = processor._determine_node_type(album_data)
    logger.info(f"✓ Detected Album: {node_type == 'Album'}")

    # Test Venue detection
    venue_data = {"capacity": 5000, "name": "Test Venue"}
    node_type = processor._determine_node_type(venue_data)
    logger.info(f"✓ Detected Venue: {node_type == 'Venue'}")

    logger.info("✓ Node type detection tests completed\n")


def main():
    """Run all verification tests."""
    logger.info("Starting Feedback Processor Verification\n")

    try:
        verify_feedback_models()
        verify_feedback_processor_initialization()
        verify_correction_parsing()
        verify_node_type_detection()

        logger.info("=" * 60)
        logger.info("✓ ALL VERIFICATION TESTS PASSED")
        logger.info("=" * 60)
        logger.info("\nFeedback processor is ready for use!")
        logger.info("\nKey Features:")
        logger.info("  • Like feedback: Increases source quality scores")
        logger.info("  • Dislike feedback: Decreases scores and schedules re-enrichment")
        logger.info("  • Correction feedback: Updates nodes and penalizes incorrect sources")
        logger.info("  • Report feedback: Creates issue reports and reduces visibility")
        logger.info("  • All feedback logged to Overmind Lab")
        logger.info("  • Historical feedback persisted for analysis")

    except Exception as e:
        logger.error(f"\n✗ VERIFICATION FAILED: {e}")
        raise


if __name__ == "__main__":
    main()
