-- Sprint B-2a: news pipeline tables.
-- vss is a DuckDB core extension (bundled since v1.1). INSTALL is idempotent.
INSTALL vss;
LOAD vss;

CREATE TABLE IF NOT EXISTS news_stories (
    id              VARCHAR PRIMARY KEY,
    url             VARCHAR,
    source          VARCHAR NOT NULL,
    headline        VARCHAR NOT NULL,
    body            VARCHAR,
    published_at    TIMESTAMP,
    fetched_at      TIMESTAMP NOT NULL,
    tickers         VARCHAR[],
    sectors         VARCHAR[],
    embedding       FLOAT[384],
    cluster_id      VARCHAR
);

CREATE TABLE IF NOT EXISTS news_clusters (
    id              VARCHAR PRIMARY KEY,
    as_of           DATE NOT NULL,
    story_count     INTEGER NOT NULL,
    source_count    INTEGER NOT NULL,
    top_tickers     VARCHAR[],
    dominant_sector VARCHAR,
    representative_id VARCHAR,
    centroid        FLOAT[384],
    first_seen      TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS news_clusters_as_of_idx ON news_clusters(as_of);

CREATE TABLE IF NOT EXISTS cluster_lineage (
    parent_id           VARCHAR NOT NULL,
    child_id            VARCHAR NOT NULL,
    day                 DATE NOT NULL,
    similarity          DOUBLE NOT NULL,
    story_count_delta   INTEGER NOT NULL,
    PRIMARY KEY (parent_id, child_id)
);
