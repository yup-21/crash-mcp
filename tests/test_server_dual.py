import pytest
from unittest.mock import MagicMock, patch
from crash_mcp.server import analyze_target, unified_sessions

@patch('crash_mcp.server.UnifiedSession')
@patch('os.path.exists')
def test_analyze_target_unified_success(mock_exists, MockUnifiedSession):
    # Setup mocks
    mock_exists.return_value = True
    
    mock_session = MockUnifiedSession.return_value
    
    # Run
    # Local path
    result = analyze_target('/tmp/vmcore', '/tmp/vmlinux')
    
    # Verify Unified Session started
    MockUnifiedSession.assert_called_with('/tmp/vmcore', '/tmp/vmlinux', remote_host=None, remote_user=None)
    mock_session.start.assert_called_once()
    
    assert "Unified Session started successfully" in result
    assert len(unified_sessions) > 0

@patch('crash_mcp.server.UnifiedSession')
def test_analyze_target_remote(MockUnifiedSession):
    mock_session = MockUnifiedSession.return_value
    
    # Remote path (no local check)
    result = analyze_target('/tmp/remote_core', '/tmp/remote_vmlinux', 
                          ssh_host='example.com', ssh_user='user')
    
    MockUnifiedSession.assert_called_with('/tmp/remote_core', '/tmp/remote_vmlinux', 
                                        remote_host='example.com', remote_user='user')
    mock_session.start.assert_called_once()
    
    assert "Unified Session started successfully" in result

@patch('crash_mcp.server.UnifiedSession')
@patch('os.path.exists')
def test_analyze_target_failure(mock_exists, MockUnifiedSession):
    mock_exists.return_value = True
    MockUnifiedSession.side_effect = Exception("Unified init failed")
    
    result = analyze_target('/tmp/vmcore', '/tmp/vmlinux')
    
    assert "Failed to start unified session" in result
