import pytest
from src.navidrome_api import NavidromeClient

@pytest.mark.asyncio
async def test_start_scan_success(mocker):
    mock_response = mocker.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"subsonic-response": {"status": "ok", "version": "1.16.1"}}
    mock_get = mocker.AsyncMock(return_value=mock_response)
    mocker.patch('src.navidrome_api.httpx.AsyncClient.get', new=mock_get)

    client = NavidromeClient(
        base_url="http://navidrome:4533",
        username="admin",
        password="password123"
    )

    result = await client.start_scan()

    assert result is True
    mock_get.assert_called_once()
    
    args, kwargs = mock_get.call_args
    assert args[0] == "http://navidrome:4533/rest/startScan"
    
    params = kwargs['params']
    assert params['u'] == "admin"
    assert params['c'] == "MediaRequestPortal"
    assert params['f'] == "json"
    assert 't' in params
    assert 's' in params
    assert 'v' in params

@pytest.mark.asyncio
async def test_start_scan_failure(mocker):
    mock_response = mocker.MagicMock()
    mock_response.status_code = 500
    mock_get = mocker.AsyncMock(return_value=mock_response)
    mocker.patch('src.navidrome_api.httpx.AsyncClient.get', new=mock_get)

    client = NavidromeClient(
        base_url="http://navidrome:4533",
        username="admin",
        password="password123"
    )

    with pytest.raises(Exception) as exc_info:
        await client.start_scan()
        
    assert "Navidrome API error" in str(exc_info.value)
