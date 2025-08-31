from services.obs_controller import OBSController

def test_obs_dry_run():
    import os
    os.environ["OBS_DRY_RUN"] = "true"
    c = OBSController()
    assert c.start_recording().ok
    assert c.stop_recording().ok
