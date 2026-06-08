# 13 · 매일 아침 brief 자동 push (macOS launchd)

PR 72는 macOS LaunchAgent로 매일 오전 9시 로컬 타임존(KST) `harness brief --push email,osnotify`를 실행한다. 기본 push 채널은 이메일과 macOS 알림이다.

## 설치

```bash
cd ~/edith
make install-morning-cron
```

설치 타깃은 `scripts/launchd/com.edith.morningbrief.plist`의 `__EDITH_HOME__` placeholder를 현재 repo 경로로 치환해 `~/Library/LaunchAgents/com.edith.morningbrief.plist`에 설치한다.

## 동작

- 스케줄: 매일 09:00, macOS 로컬 타임존 기준. 사용자의 macOS 타임존이 KST면 오전 9시 KST에 실행된다.
- catch-up: launchd `StartCalendarInterval` job은 노트북이 잠자느라 놓친 실행을 깨어날 때 한 번 실행한다. 별도 설정은 필요 없다.
- 실행 스크립트: `scripts/morning_push.sh`
- 로그: `logs/morning_push.log`, `logs/morning_push.launchd.out.log`, `logs/morning_push.launchd.err.log`

## 사전 설정

이메일 push에는 `.env`의 `EDITH_NOTIFY_EMAIL`과 Gmail OAuth 토큰이 필요하다. 설정이 빠진 채널은 실패로 기록되지만, 다른 채널은 계속 전송한다.

카톡 자동 push를 쓰려면 `docs/11_kakao_setup.md`의 KakaoClient 토큰 세팅이 필요하다. PlayMCP는 대화형 세션 전용이라 launchd cron에서 사용할 수 없다.

## 제거

```bash
cd ~/edith
make uninstall-morning-cron
```

## 즉시 수동 테스트

```bash
scripts/morning_push.sh
tail -f logs/morning_push.log
```
