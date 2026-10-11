from app.config import ProfileConfig
from app.pipeline.matcher import compute_profile_hash


def test_profile_hash_is_deterministic():
    profile = ProfileConfig(skills=["Python"])
    assert compute_profile_hash(profile, "deepseek-chat") == compute_profile_hash(
        profile, "deepseek-chat"
    )


def test_profile_hash_changes_with_profile_and_model():
    base = ProfileConfig(skills=["Python"])
    assert compute_profile_hash(base, "deepseek-chat") != compute_profile_hash(
        ProfileConfig(skills=["Go"]), "deepseek-chat"
    )
    assert compute_profile_hash(base, "deepseek-chat") != compute_profile_hash(
        base, "other-model"
    )
