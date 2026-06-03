// lib/db/projects.ts  [신규] — 서버 전용 프로젝트 쿼리 헬퍼.
// 호출자가 createSupabaseServer()로 만든 클라이언트를 넘긴다(인증/RLS는 그 세션 기준).

import type { SupabaseClient } from "@supabase/supabase-js";
import type { BizInfo, SectionCopy, TemplateId } from "@/lib/ai/types";

export interface ProjectRow {
  id: string;
  owner: string;
  slug: string;
  title: string;
  prompt: string;
  template: TemplateId;
  biz_info: BizInfo;
  copy: SectionCopy;
  published: boolean;
  created_at: string;
  updated_at: string;
}

export interface NewProject {
  title: string;
  prompt: string;
  template: TemplateId;
  biz_info: BizInfo;
  copy: SectionCopy;
  publish?: boolean;
}

/** 사람이 읽기 쉬운 + 충돌 적은 slug 생성(ASCII 영숫자 + 랜덤 접미). */
export function slugify(base: string): string {
  const ascii = base
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
  const rand = Math.random().toString(36).slice(2, 7);
  return `${ascii || "page"}-${rand}`;
}

export async function insertProject(
  supabase: SupabaseClient,
  owner: string,
  input: NewProject,
): Promise<ProjectRow> {
  const title = input.title || input.biz_info.service_name || "제목 없는 페이지";
  const { data, error } = await supabase
    .from("projects")
    .insert({
      owner,
      slug: slugify(title),
      title,
      prompt: input.prompt,
      template: input.template,
      biz_info: input.biz_info,
      copy: input.copy,
      published: input.publish ?? true,
    })
    .select()
    .single();
  if (error) throw new Error(error.message);
  return data as ProjectRow;
}

export async function selectMyProjects(supabase: SupabaseClient): Promise<ProjectRow[]> {
  const { data, error } = await supabase
    .from("projects")
    .select("*")
    .order("created_at", { ascending: false });
  if (error) throw new Error(error.message);
  return (data ?? []) as ProjectRow[];
}

/** 공개 게시된 프로젝트를 slug로 조회(비로그인도 RLS 정책상 select 허용). */
export async function selectPublishedBySlug(
  supabase: SupabaseClient,
  slug: string,
): Promise<ProjectRow | null> {
  const { data, error } = await supabase
    .from("projects")
    .select("*")
    .eq("slug", slug)
    .eq("published", true)
    .maybeSingle();
  if (error) throw new Error(error.message);
  return (data as ProjectRow) ?? null;
}

/** 소유자 기준 단건 조회(대시보드/리드 페이지에서 제목 확인 등). */
export async function selectMyProjectById(
  supabase: SupabaseClient,
  id: string,
): Promise<ProjectRow | null> {
  const { data, error } = await supabase.from("projects").select("*").eq("id", id).maybeSingle();
  if (error) throw new Error(error.message);
  return (data as ProjectRow) ?? null;
}
