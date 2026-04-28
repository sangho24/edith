# scripts/

Edith 운영 스크립트.

## `install_daily.sh` — Daily compile loop 설치 (macOS launchd)

매일 22시 `harness daily` 가 자동 실행되도록 설정.
실행 내용: compile (raw → wiki) + eval (regression) + dashboard + log.md append.

### 설치

```bash
cd ~/edith
bash scripts/install_daily.sh
```

설치되는 곳: `~/Library/LaunchAgents/com.edith.daily.plist`
로그: `~/edith/harness/daily.log` (gitignore 됨)

### 즉시 한 번 실행 (테스트)

```bash
bash scripts/install_daily.sh test
```

### 제거

```bash
bash scripts/install_daily.sh uninstall
```

### 시간 변경

`scripts/com.edith.daily.plist.template` 의 `StartCalendarInterval` Hour/Minute 수정 후 재설치.

## Linux/cron 대안

macOS가 아닌 환경 (홈허브 Linux 등):

```bash
crontab -e
# 추가:
0 22 * * * cd ~/edith && /usr/local/bin/uv run harness daily >> harness/daily.log 2>&1
```

## 환경 변수

- `EDITH_HOME` — repo 위치 (default: `$HOME/edith`)
- `ANTHROPIC_API_KEY` — daily가 LLM 호출하므로 필요. `~/edith/.env` 또는 `launchctl setenv` 로 주입.

> 주의: launchd는 shell rc 파일을 안 읽음. `.env` 로딩이 필요하면 plist에 직접 추가하거나
> `harness daily` 진입점에서 `python-dotenv` 자동 로딩 (Phase 3에서 추가 예정).
