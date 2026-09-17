# Test connection before storing
        app_logger.info(f"Testing connection for {connection_id}")
        is_valid, error_message = await connection_service.test_connection(credentials)
        if not is_valid:
            detail = error_message or "Failed to connect to database with provided credentials"
            raise HTTPException(
                status_code=400,
                detail=detail
            )