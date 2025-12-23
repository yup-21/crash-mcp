import pytest
from unittest.mock import MagicMock, patch
from crash_mcp.server import analyze_target, sessions, drgn_sessions

@patch('crash_mcp.server.CrashSession')
@patch('crash_mcp.server.DrgnSession')
@patch('os.path.exists')
def test_analyze_target_dual_success(mock_exists, MockDrgnSession, MockCrashSession):
    # Setup mocks
    mock_exists.return_value = True
    
    mock_crash = MockCrashSession.return_value
    mock_drgn = MockDrgnSession.return_value
    
    # Run
    result = analyze_target('/tmp/vmcore', '/tmp/vmlinux')
    
    # Verify Crash Session started
    MockCrashSession.assert_called_with('/tmp/vmcore', '/tmp/vmlinux')
    mock_crash.start.assert_called_once()
    
    # Verify Drgn Session started
    MockDrgnSession.assert_called_with('/tmp/vmcore', '/tmp/vmlinux')
    mock_drgn.start.assert_called_once()
    
    # Verify output contains both
    assert "Crash Session: Started" in result
    assert "Drgn Session: Started" in result
    
    # Verify both are in global state (we might need to check the IDs from internal logic, 
    # but the mocks are freshly created so checking side effects on the dicts is tricky 
    # if we don't clear them or know the IDs.
    # However, standard usage of _start_session_internal updates the global dicts.)
    assert len(sessions) > 0
    assert len(drgn_sessions) > 0

@patch('crash_mcp.server.CrashSession')
@patch('crash_mcp.server.DrgnSession')
@patch('os.path.exists')
def test_analyze_target_partial_failure(mock_exists, MockDrgnSession, MockCrashSession):
    mock_exists.return_value = True
    
    # Crash succeeds
    mock_crash = MockCrashSession.return_value
    
    # Drgn fails
    MockDrgnSession.side_effect = Exception("Drgn failed")
    
    result = analyze_target('/tmp/vmcore', '/tmp/vmlinux')
    
    assert "Crash Session: Started" in result
    assert "Drgn Session: Failed (Drgn failed)" in result
