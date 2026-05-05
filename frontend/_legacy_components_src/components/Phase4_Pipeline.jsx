/**
 * Phase 4 Pipeline Component
 * Displays generated title, thumbnail, and description suggestions with copy buttons
 */

import React, { useState, useEffect } from 'react';
import './Phase4_Pipeline.css';


const Phase4Pipeline = ({ jobId, initialData }) => {
  const [job, setJob] = useState(initialData || null);
  const [loading, setLoading] = useState(!initialData);
  const [error, setError] = useState(null);
  const [copiedSection, setCopiedSection] = useState(null);

  useEffect(() => {
    if (!initialData && jobId) {
      fetchJob(jobId);
    }
  }, [jobId, initialData]);

  const fetchJob = async (id) => {
    try {
      setLoading(true);
      const response = await fetch(`/api/job/${id}`);
      if (!response.ok) throw new Error('Failed to fetch job');
      const data = await response.json();
      setJob(data);
      setError(null);
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  };

  const copyToClipboard = (text, section) => {
    navigator.clipboard.writeText(text);
    setCopiedSection(section);
    setTimeout(() => setCopiedSection(null), 2000);
  };

  if (loading) {
    return (
      <div className="phase4-pipeline loading">
        <p>パイプライン処理中...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="phase4-pipeline error">
        <p>エラーが発生しました: {error}</p>
      </div>
    );
  }

  if (!job) {
    return <div className="phase4-pipeline">データがありません</div>;
  }

  const { selectedTitle, description, titleSuggestions } = job;

  return (
    <div className="phase4-pipeline">
      <div className="pipeline-container">
        {/* Title Section */}
        <section className="pipeline-section title-section">
          <h2>動画タイトル</h2>
          <div className="content-box title-box">
            <p className="selected-title">{selectedTitle}</p>
            <button
              className={`copy-button ${copiedSection === 'title' ? 'copied' : ''}`}
              onClick={() => copyToClipboard(selectedTitle, 'title')}
            >
              {copiedSection === 'title' ? 'コピーしました！' : 'コピー'}
            </button>
          </div>

          {titleSuggestions && titleSuggestions.length > 0 && (
            <div className="suggestions">
              <h3>その他の候補</h3>
              <ul>
                {titleSuggestions.map((title, idx) => (
                  <li key={idx}>{title}</li>
                ))}
              </ul>
            </div>
          )}
        </section>

        {/* Description Section */}
        {description && (
          <section className="pipeline-section description-section">
            <h2>YouTube説明文</h2>

            {/* Full Description */}
            <div className="content-box full-description-box">
              <div className="description-header">
                <h3>完全版</h3>
                <button
                  className={`copy-button ${copiedSection === 'full' ? 'copied' : ''}`}
                  onClick={() => copyToClipboard(description.full_description, 'full')}
                >
                  {copiedSection === 'full' ? 'コピーしました！' : 'コピー'}
                </button>
              </div>
              <div className="description-text">
                <pre>{description.full_description}</pre>
              </div>
            </div>

            {/* Summary Section */}
            {description.summary && (
              <div className="description-subsection">
                <div className="subsection-header">
                  <h4>概要</h4>
                  <button
                    className={`copy-button small ${copiedSection === 'summary' ? 'copied' : ''}`}
                    onClick={() => copyToClipboard(description.summary, 'summary')}
                  >
                    {copiedSection === 'summary' ? '✓' : 'コピー'}
                  </button>
                </div>
                <pre className="subsection-text">{description.summary}</pre>
              </div>
            )}

            {/* Timestamps Section */}
            {description.timestamps && (
              <div className="description-subsection">
                <div className="subsection-header">
                  <h4>タイムスタンプ</h4>
                  <button
                    className={`copy-button small ${copiedSection === 'timestamps' ? 'copied' : ''}`}
                    onClick={() => copyToClipboard(description.timestamps, 'timestamps')}
                  >
                    {copiedSection === 'timestamps' ? '✓' : 'コピー'}
                  </button>
                </div>
                <pre className="subsection-text">{description.timestamps}</pre>
              </div>
            )}

            {/* Channel Info Section */}
            {description.channel_info && (
              <div className="description-subsection">
                <div className="subsection-header">
                  <h4>チャンネル情報</h4>
                  <button
                    className={`copy-button small ${copiedSection === 'channel' ? 'copied' : ''}`}
                    onClick={() => copyToClipboard(description.channel_info, 'channel')}
                  >
                    {copiedSection === 'channel' ? '✓' : 'コピー'}
                  </button>
                </div>
                <pre className="subsection-text">{description.channel_info}</pre>
              </div>
            )}

            {/* Hashtags Section */}
            {description.hashtags && (
              <div className="description-subsection">
                <div className="subsection-header">
                  <h4>ハッシュタグ</h4>
                  <button
                    className={`copy-button small ${copiedSection === 'hashtags' ? 'copied' : ''}`}
                    onClick={() => copyToClipboard(description.hashtags, 'hashtags')}
                  >
                    {copiedSection === 'hashtags' ? '✓' : 'コピー'}
                  </button>
                </div>
                <p className="subsection-text">{description.hashtags}</p>
              </div>
            )}
          </section>
        )}

        {/* Thumbnail Section (placeholder) */}
        <section className="pipeline-section thumbnail-section">
          <h2>サムネイル</h2>
          <div className="content-box thumbnail-box">
            <p className="placeholder">サムネイル生成予定</p>
          </div>
        </section>
      </div>
    </div>
  );
};

export default Phase4Pipeline;
