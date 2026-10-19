-- agent-memory read API. The database is a read-only mirror of the files; every write goes to the files.
--
-- SurrealDB 3.3.4: an indexed field (kind, status, project) and a graph condition (->about->...) in ONE
-- WHERE can silently return too few rows. These functions fetch through the graph edge first and filter
-- that list, which no index touches. Do the same in your own queries (agent_memory/canary.py checks it).

-- Open threads ("## Open threads" in any NOW.md), optionally only those that mention $who.
DEFINE FUNCTION OVERWRITE fn::waiting_on($who: option<string>) {
    RETURN SELECT VALUE project + " · " + text FROM entry
           WHERE kind = 'open_thread' AND status = 'active' AND block = 'item' AND text != 'none'
             AND ($who = NONE OR string::contains(string::lowercase(text), string::lowercase($who)))
           ORDER BY project;
};

-- Keyword search; hybrid (keyword + vector, fused by reciprocal rank) when $qv, the question embedded
-- with the same model as emb, is given. `agent-memory search` embeds the question and passes it.
-- Archived files and superseded memories are left out. The knn K is a literal (3.3.4 rejects a
-- parameter there): 40 candidates, cut to $limit after fusing.
DEFINE FUNCTION OVERWRITE fn::search($q: string, $limit: option<int>, $qv: option<array<float>>) {
    LET $n = $limit ?? 20;
    LET $kw = SELECT id, project, kind, path, line, text, search::score(1) AS score FROM entry
              WHERE text @1@ $q AND status = 'active' AND source.archived != true AND source.superseded_by = NONE
              ORDER BY score DESC LIMIT $n;
    IF $qv IS NONE { RETURN $kw; };
    LET $vec = SELECT type::record('entry', record::id(id)) AS id, vector::distance::knn() AS distance
               FROM emb WHERE v <|40,100|> $qv ORDER BY distance;
    RETURN search::rrf([$vec, $kw], $n, 60)
        .filter(|$r| $r.id.status = 'active' AND $r.id.source.archived != true AND $r.id.source.superseded_by = NONE)
        .map(|$r| { id: $r.id, project: $r.id.project, kind: $r.id.kind, path: $r.id.path, line: $r.id.line,
                    text: $r.id.text, score: $r.rrf_score });
};

-- One project's entries of one kind ('decision', 'decided_against', 'open_thread', 'gotcha', ...), in file order.
DEFINE FUNCTION OVERWRITE fn::entries($project: string, $kind: option<string>) {
    LET $ids = (SELECT VALUE <-about<-entry FROM ONLY type::record('project', $project)) ?? [];
    RETURN SELECT VALUE text FROM $ids WHERE status = 'active' AND ($kind = NONE OR kind = $kind) ORDER BY path, ord;
};

-- One project's LOG lines, newest first.
DEFINE FUNCTION OVERWRITE fn::logs($project: string, $limit: option<int>) {
    LET $ids = (SELECT VALUE <-about<-log FROM ONLY type::record('project', $project)) ?? [];
    RETURN SELECT VALUE raw FROM $ids WHERE status = 'active' ORDER BY ord DESC LIMIT $limit ?? 10;
};

-- Every LOG line one session wrote, in order ('s:1a2b3c4d').
DEFINE FUNCTION OVERWRITE fn::session($tag: string) {
    LET $ids = (SELECT VALUE <-written_in<-log FROM ONLY type::record('session', $tag)) ?? [];
    RETURN SELECT VALUE raw FROM $ids WHERE status = 'active' ORDER BY ord;
};

-- NOW.md files untouched for $days (default 14) or more, oldest first: "project · YYYY-MM-DD".
DEFINE FUNCTION OVERWRITE fn::stale_nows($days: option<int>) {
    LET $cut = time::now() - <duration> (<string> ($days ?? 14) + "d");
    RETURN SELECT VALUE project + " · " + time::format(mtime, "%Y-%m-%d") FROM source
           WHERE kind = 'now' AND status = 'active' AND archived = false AND mtime < $cut ORDER BY mtime;
};

-- Claims written down as not verified, in every NOW.md: "project · text".
DEFINE FUNCTION OVERWRITE fn::unverified() {
    RETURN SELECT VALUE project + " · " + text FROM entry
           WHERE status = 'active' AND block = 'item' AND string::ends_with(path, "NOW.md")
             AND (string::contains(string::lowercase(text), "not verified") OR string::contains(text, "UNVERIFIED")
                  OR string::contains(string::lowercase(text), "claimed, not"))
           ORDER BY project;
};

-- Items and memories whose review date has passed, oldest first. $today defaults to today (UTC).
DEFINE FUNCTION OVERWRITE fn::overdue($today: option<string>) {
    LET $d = $today ?? time::format(time::now(), "%Y-%m-%d");
    RETURN SELECT project, review_by, text, path FROM entry
           WHERE status = 'active' AND block IN ['item', 'frontmatter', 'section'] AND review_by != NONE
             AND review_by <= $d AND source.archived != true
           ORDER BY review_by, project;
};

-- What a memory replaced and what replaced it, and the memories that contradict each other (open conflicts).
DEFINE FUNCTION OVERWRITE fn::history($name: string) {
    RETURN SELECT name, project, path, ->supersedes->source.name AS replaces, superseded_by.name AS replaced_by
           FROM source WHERE kind = 'memory' AND status = 'active' AND name = $name;
};
DEFINE FUNCTION OVERWRITE fn::conflicts() {
    RETURN SELECT in.name AS memory, out.name AS contradicts, in.project AS project FROM contradicts
           WHERE in.status = 'active' AND out.status = 'active';
};
