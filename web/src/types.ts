export type Rect = [number, number, number, number];
export type Anchor = {
  sha256: string;
  page: number;
  kind: "text" | "region" | "page";
  rects: Rect[];
  quote: string;
};
export type Paper = {
  id: string;
  title: string;
  sha256: string;
  page_count: number;
  current_page: number;
  source: Record<string, unknown>;
  citation_key: string;
  tags: string[];
};
export type ExternalSource = {
  citation: string;
  title: string;
  authors: string[];
  year: string | number | null;
  url: string;
  locator: string;
  quote: string;
  source_type: string;
  provider: string;
  arxiv_id: string | null;
  retrieved_at: string;
};
export type Thread = { id: string; title: string };
export type Context = {
  sources: {
    page: number;
    paragraph?: number;
    citation?: string;
    text: string;
    reason: string;
    truncated: boolean;
    anchor?: Anchor | null;
  }[];
  characters: number;
  history_messages: number;
  scope: string;
  image_attached: boolean;
  anchor: Anchor | null;
  external_sources?: ExternalSource[];
  coverage?: {
    pages_included: number[];
    total_pages: number;
    extractable_pages?: number;
    complete_text?: boolean;
  };
};
export type Message = {
  id: string;
  role: string;
  content: string;
  status: string;
  model: string | null;
  anchor: Anchor | null;
  context: Context | null;
};
export type Note = {
  id: string;
  content: string;
  message_id: string | null;
  anchor: Anchor | null;
  paper_id: string;
  paper_title?: string;
  paper_sha256?: string;
  paper_page_count?: number;
};
export type Provider = {
  provider: string;
  base_url: string;
  model: string;
  supports_images: boolean;
  effort: string;
  max_tokens: number;
};
export type Status = {
  configured: boolean;
  data_dir: string | null;
  key_configured: boolean;
  key_storage: "keychain" | "environment" | "none" | "unavailable";
  token: string;
  poppler_ready: boolean;
  provider: Provider;
};
export type Run = {
  id: string;
  message_id: string;
  workflow: string;
  status: string;
  provider: string;
  model: string;
  error: string | null;
  trace:
    | {
        schema_version: number;
        stages: {
          phase: string;
          status: string;
          model: string;
          content: string;
        }[];
      }
    | null;
  usage:
    | {
        phase: string;
        model: string;
        tokens: Record<string, number> | null;
        finish_reason: string | null;
      }[]
    | null;
};
export type Candidate = {
  arxiv_id: string;
  title: string;
  authors: string[];
  year: string;
  url: string;
};
