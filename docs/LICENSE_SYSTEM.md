# 통합 라이선스(코드발급) 시스템

윈도우 설치형 자동화 봇 **6개**를 하나로 묶어, **코드 1개로 전부 잠금 해제**하는 온라인 라이선스 시스템입니다.
관리자가 웹에서 코드를 발급하고, 각 봇은 실행 시 서버에 코드를 검증합니다.

```
[관리자] /admin/licenses 에서 코드 발급
            │  ALLB-XXXXX-XXXXX-XXXXX
            ▼
[고객] 봇에 코드 입력 → 봇이 POST /api/license/verify { code, device_id, bot_id }
            ▼
[서버] 유효성 검사(정지/만료/기기수) → { valid, reason, license }
```

## 1. 구성요소

| 영역 | 경로 |
|---|---|
| 관리 화면 | `/admin/licenses` (서버 컴포넌트, 관리자 전용) |
| 발급/관리 API | `/api/admin/licenses`, `/api/admin/licenses/[id]` |
| 봇 검증 API(공개) | `POST /api/license/verify` |
| DB 스키마 | `database/license-schema.sql` |
| 코어 로직 | `lib/license/*` |

## 2. 설정 (한 번만)

1. **Supabase SQL Editor** 에서 `database/license-schema.sql` 전체 실행.
2. 환경변수(`.env.local` 또는 Vercel)에 입력:
   ```
   NEXT_PUBLIC_SUPABASE_URL=...
   NEXT_PUBLIC_SUPABASE_ANON_KEY=...
   SUPABASE_SERVICE_ROLE_KEY=...        # 서버 전용
   LICENSE_ADMIN_EMAILS=me@example.com  # 관리자 이메일(쉼표 구분)
   # 선택: 봇 이름 커스터마이즈
   # LICENSE_BOTS=kakao:카카오봇,insta:인스타봇,naver:네이버봇,...
   ```
3. `LICENSE_ADMIN_EMAILS` 에 넣은 이메일로 회원가입/로그인 후 `/admin/licenses` 접속.

> **보안:** 라이선스 테이블은 RLS 를 켜고 정책을 두지 않아, `service_role` 키를 쓰는 서버만 접근합니다.
> 관리 화면은 `로그인 + 관리자 허용목록`을 통과해야 열립니다. service_role 키는 절대 클라이언트에 노출하지 마세요.

## 3. 봇 검증 API

### 요청
```
POST /api/license/verify
Content-Type: application/json

{
  "code": "ALLB-XXXXX-XXXXX-XXXXX",   // 필수. 대시 없이 보내도 됨
  "device_id": "<기기 고유 지문>",     // 권장. 기기 수 제한에 사용
  "bot_id": "bot1",                    // 선택. 어떤 봇이 호출했는지(로그/통계)
  "device_label": "DESKTOP-ABC"        // 선택. 표시용 호스트명 등
}
```

### 응답 (비즈니스 결과는 항상 HTTP 200)
```jsonc
// 유효
{ "valid": true, "reason": "ok", "message": "인증되었습니다.",
  "license": { "label": "...", "status": "active", "expires_at": null,
               "bots": ["bot1","bot2","bot3","bot4","bot5","bot6"],
               "devices": { "used": 1, "max": 1 } } }

// 무효 (reason 으로 분기)
{ "valid": false, "reason": "expired",       "message": "만료된 코드입니다." }
{ "valid": false, "reason": "revoked",       "message": "정지된 코드입니다." }
{ "valid": false, "reason": "not_found",     "message": "존재하지 않는 코드입니다." }
{ "valid": false, "reason": "device_limit",  "message": "허용 기기 수를 초과했습니다." }
```
4xx/5xx 는 잘못된 요청(`400`)·한도 초과(`429`)·미설정(`503`)·서버 오류(`500`) 에만 사용합니다.

### `device_id` (기기 지문) 만들기
기기마다 안정적으로 동일한 값이어야 합니다. 윈도우 권장:
- 레지스트리 `HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid`, 또는
- 메인보드/디스크 볼륨 시리얼을 조합해 SHA-256 해시.

## 4. 봇(C#/.NET) 연동 예시

```csharp
using System.Net.Http;
using System.Net.Http.Json;

public record VerifyResponse(bool valid, string reason, string message);

public static class License
{
    static readonly HttpClient http = new();
    const string ApiBase = "https://<your-app>.vercel.app";
    const string BotId = "bot1"; // 이 봇의 id

    public static async Task<bool> CheckAsync(string code)
    {
        var deviceId = GetMachineGuid(); // 위 "기기 지문" 참고
        var res = await http.PostAsJsonAsync($"{ApiBase}/api/license/verify", new {
            code, device_id = deviceId, bot_id = BotId,
            device_label = Environment.MachineName
        });

        var data = await res.Content.ReadFromJsonAsync<VerifyResponse>();
        if (data is null) return false;
        if (!data.valid)
        {
            // reason: not_found / revoked / expired / device_limit ...
            MessageBox.Show(data.message);
            return false;
        }
        return true; // 통과 → 봇 기능 활성화
    }

    static string GetMachineGuid()
    {
        using var key = Microsoft.Win32.Registry.LocalMachine
            .OpenSubKey(@"SOFTWARE\Microsoft\Cryptography");
        return key?.GetValue("MachineGuid")?.ToString() ?? Environment.MachineName;
    }
}
```

> **운영 팁:** 봇 시작 시 1회 검증 후, 장시간 실행되는 봇이라면 수십 분~수 시간 간격으로 재검증하면
> 정지/만료를 빠르게 반영할 수 있습니다. 네트워크 일시 단절 대비 짧은 grace(예: 마지막 성공 후 N시간)는
> 봇 측에서 선택적으로 둘 수 있습니다.

## 5. 관리 작업

| 작업 | 방법 |
|---|---|
| 코드 발급 | 화면 상단 폼(라벨·허용 기기 수·유효기간) → **+ 코드 발급** |
| 정지/재개 | 목록의 **정지** / **재개** (정지 시 봇 인증 즉시 차단) |
| 기기 초기화 | **기기초기화** — 고객 PC 교체 시. 다음 실행부터 새 기기 재등록 |
| 삭제 | **삭제** — 코드·기기·로그 영구 삭제(복구 불가) |

## 6. 향후 확장(2차)
- 결제(Toss/Stripe) 연동 → 자가결제 후 자동 발급
- 봇별 개별 코드 / 플랜(기본·프로) 구분
- 오프라인 서명 키(서버 무관 검증) 병행
- 검증 로그(`license_checks`) 기반 사용 통계 대시보드
