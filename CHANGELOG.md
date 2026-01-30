# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Implementation plan with 10 phases covering full invoice automation workflow
- Plan review document with iterative quality assessment

### Changed
- Expanded WorkflowData model with thread IDs, attachment paths, and timeout tracking
- Added Cancel state transitions for PENDING_INIT_APPROVAL and ALL_DOCS_READY states
- Added WAITING_DOCS timeout handling with 7/14-day reminders
- Added verification steps to all implementation phases
- Specified email monitor error handling (rate limits, network, auth)
- Specified Playwright browser lifecycle management
- Specified Docker volume permissions
- Added Telegram edit flow input validation
- Added event handler concurrency controls (asyncio.Queue)
- Added Gemini API graceful degradation behavior
