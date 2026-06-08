// scripts/threads-test/_assert.ts — 가상 테스트용 초경량 단언 헬퍼(테스트 프레임워크 없이 tsx로 실행).

let passed = 0;
let failed = 0;

export function ok(name: string, cond: boolean): void {
  if (cond) {
    passed++;
    console.log("  ✓ " + name);
  } else {
    failed++;
    console.log("  ✗ " + name);
  }
}

export function eq<T>(name: string, got: T, want: T): void {
  const good = got === want;
  ok(name + (good ? "" : ` (want ${JSON.stringify(want)}, got ${JSON.stringify(got)})`), good);
}

export function contains(name: string, hay: string, needle: string): void {
  ok(name, typeof hay === "string" && hay.includes(needle));
}

export function summary(label: string): void {
  console.log(`\n${label}: ${passed} passed, ${failed} failed`);
  if (failed > 0) process.exit(1);
  console.log("✅ PASS");
}
