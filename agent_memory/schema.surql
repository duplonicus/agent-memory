-- agent-memory schema. Applied as root by `agent-memory schema`; every statement is idempotent.
--
-- A `source` is one file (CLAUDE.md, a rules file, a NOW.md, LOG.md, a memory file, a note).
-- An `entry` is one block of it (heading, bullet, paragraph, code fence, table, frontmatter), with
-- `raw` holding the exact bytes and `text` a cleaned copy for search. A `log` is one LOG.md line.
-- The files are the source of truth; this database is a read-only mirror the sync daemon keeps level.

DEFINE TABLE OVERWRITE source SCHEMAFULL;
DEFINE FIELD OVERWRITE path        ON source TYPE string;
DEFINE FIELD OVERWRITE kind        ON source TYPE string
  ASSERT $value IN ['rules','memory','memory_index','now','log','doc','project_claude'];
DEFINE FIELD OVERWRITE project     ON source TYPE string;
DEFINE FIELD OVERWRITE projects    ON source TYPE array<string> DEFAULT [];   -- canonical names, for edges
DEFINE FIELD OVERWRITE locator     ON source TYPE string;                     -- what the ids hash; survives moves
DEFINE FIELD OVERWRITE bytes       ON source TYPE int;
DEFINE FIELD OVERWRITE sha256      ON source TYPE string;
DEFINE FIELD OVERWRITE mtime       ON source TYPE datetime;
DEFINE FIELD OVERWRITE imported_at ON source TYPE datetime;
DEFINE FIELD OVERWRITE archived    ON source TYPE bool DEFAULT false;         -- kept, but no vector and no search hit
DEFINE FIELD OVERWRITE name        ON source TYPE option<string>;             -- memory frontmatter
DEFINE FIELD OVERWRITE description ON source TYPE option<string>;
DEFINE FIELD OVERWRITE mem_type    ON source TYPE option<string>;             -- user | feedback | project | reference
DEFINE FIELD OVERWRITE supersedes  ON source TYPE array<string> DEFAULT [];   -- memory names, from frontmatter
DEFINE FIELD OVERWRITE contradicts ON source TYPE array<string> DEFAULT [];
DEFINE FIELD OVERWRITE superseded_by ON source TYPE option<record<source>>;
DEFINE FIELD OVERWRITE review_by   ON source TYPE option<string>;             -- YYYY-MM-DD
DEFINE FIELD OVERWRITE status      ON source TYPE string DEFAULT 'active' ASSERT $value IN ['active','deleted'];
DEFINE INDEX OVERWRITE source_path ON source FIELDS path;
DEFINE INDEX OVERWRITE source_project ON source FIELDS project;

DEFINE TABLE OVERWRITE entry SCHEMAFULL;
DEFINE FIELD OVERWRITE source      ON entry TYPE record<source>;
DEFINE FIELD OVERWRITE path        ON entry TYPE string;
DEFINE FIELD OVERWRITE project     ON entry TYPE string;
DEFINE FIELD OVERWRITE ord         ON entry TYPE float;                       -- order inside the file
DEFINE FIELD OVERWRITE line        ON entry TYPE int;                         -- 1-based line at import
DEFINE FIELD OVERWRITE kind        ON entry TYPE string
  ASSERT $value IN ['heading','frontmatter','preamble','code','table','blank','rule','project_rule',
                    'state','where','next','decision','decided_against','open_thread','gotcha','note',
                    'memory_user','memory_feedback','memory_project','memory_reference','memory_index',
                    'doc_section'];
DEFINE FIELD OVERWRITE block       ON entry TYPE string
  ASSERT $value IN ['heading','frontmatter','item','para','code','table','blank','section'];
DEFINE FIELD OVERWRITE level       ON entry TYPE option<int>;
DEFINE FIELD OVERWRITE depth       ON entry TYPE option<int>;
DEFINE FIELD OVERWRITE section     ON entry TYPE array<string> DEFAULT [];    -- heading path
DEFINE FIELD OVERWRITE text        ON entry TYPE string;
DEFINE FIELD OVERWRITE raw         ON entry TYPE string;
DEFINE FIELD OVERWRITE why         ON entry TYPE option<string>;
DEFINE FIELD OVERWRITE how_to_apply ON entry TYPE option<string>;
DEFINE FIELD OVERWRITE status      ON entry TYPE string DEFAULT 'active' ASSERT $value IN ['active','superseded'];
DEFINE FIELD OVERWRITE valid_from  ON entry TYPE datetime;
DEFINE FIELD OVERWRITE valid_to    ON entry TYPE option<datetime>;
DEFINE FIELD OVERWRITE recorded_at ON entry TYPE datetime;
DEFINE FIELD OVERWRITE review_by   ON entry TYPE option<string>;              -- from "(review by YYYY-MM-DD)"
DEFINE INDEX OVERWRITE entry_source ON entry FIELDS source;
DEFINE INDEX OVERWRITE entry_project ON entry FIELDS project;
DEFINE INDEX OVERWRITE entry_kind ON entry FIELDS kind;
DEFINE INDEX OVERWRITE entry_status ON entry FIELDS status;

DEFINE ANALYZER OVERWRITE en TOKENIZERS blank, class, punct FILTERS lowercase, ascii, snowball(english);
DEFINE INDEX OVERWRITE entry_text ON entry FIELDS text FULLTEXT ANALYZER en BM25 HIGHLIGHTS;

-- One vector per active entry, under the entry's own key (entry ids are content-addressed, so a key
-- that exists is current). 768 = embeddinggemma; another model needs this DIMENSION changed.
DEFINE TABLE OVERWRITE emb SCHEMAFULL;
DEFINE FIELD OVERWRITE v     ON emb TYPE array<float>;
DEFINE FIELD OVERWRITE model ON emb TYPE string;
DEFINE INDEX OVERWRITE emb_v ON emb FIELDS v HNSW DIMENSION 768 DIST COSINE;

DEFINE TABLE OVERWRITE log SCHEMAFULL;
DEFINE FIELD OVERWRITE source      ON log TYPE record<source>;
DEFINE FIELD OVERWRITE ord         ON log TYPE float;
DEFINE FIELD OVERWRITE line        ON log TYPE int;
DEFINE FIELD OVERWRITE day         ON log TYPE string;
DEFINE FIELD OVERWRITE surface     ON log TYPE string;
DEFINE FIELD OVERWRITE project     ON log TYPE string;                        -- as written ("api + web")
DEFINE FIELD OVERWRITE summary     ON log TYPE string;
DEFINE FIELD OVERWRITE tag         ON log TYPE option<string>;                -- s:<first 8 of the session id>
DEFINE FIELD OVERWRITE raw         ON log TYPE string;
DEFINE FIELD OVERWRITE status      ON log TYPE string DEFAULT 'active' ASSERT $value IN ['active','superseded'];
DEFINE FIELD OVERWRITE recorded_at ON log TYPE datetime;
DEFINE INDEX OVERWRITE log_source ON log FIELDS source;
DEFINE INDEX OVERWRITE log_tag ON log FIELDS tag;
DEFINE INDEX OVERWRITE log_summary ON log FIELDS summary FULLTEXT ANALYZER en BM25 HIGHLIGHTS;

DEFINE TABLE OVERWRITE project SCHEMAFULL;
DEFINE FIELD OVERWRITE name        ON project TYPE string;
DEFINE FIELD OVERWRITE now_path    ON project TYPE option<string>;

DEFINE TABLE OVERWRITE session SCHEMAFULL;
DEFINE FIELD OVERWRITE tag         ON session TYPE string;

DEFINE TABLE OVERWRITE about       TYPE RELATION IN entry|log OUT project SCHEMAFULL;
DEFINE INDEX OVERWRITE about_unique ON about FIELDS in, out UNIQUE;
DEFINE TABLE OVERWRITE written_in  TYPE RELATION IN log OUT session SCHEMAFULL;
DEFINE INDEX OVERWRITE written_in_unique ON written_in FIELDS in, out UNIQUE;
DEFINE TABLE OVERWRITE supersedes  TYPE RELATION IN source OUT source SCHEMAFULL;
DEFINE TABLE OVERWRITE contradicts TYPE RELATION IN source OUT source SCHEMAFULL;
