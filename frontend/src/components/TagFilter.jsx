import React, { useState, useMemo } from 'react';
import { Search, X, CheckSquare, Square } from 'lucide-react';
import { t } from './ui';

/**
 * TagFilter component for selecting multiple tags with search functionality
 */
const TagFilter = ({ allTags = [], selectedTags = [], onTagsChange, tagColors = {} }) => {
    const [searchQuery, setSearchQuery] = useState('');

    const filteredTags = useMemo(() => {
        if (!searchQuery.trim()) return allTags;
        const query = searchQuery.toLowerCase();
        return allTags.filter(tag => tag.toLowerCase().includes(query));
    }, [allTags, searchQuery]);

    const handleToggleTag = (tag) => {
        if (selectedTags.includes(tag)) {
            onTagsChange(selectedTags.filter(t => t !== tag));
        } else {
            onTagsChange([...selectedTags, tag]);
        }
    };

    const handleSelectAll = () => onTagsChange([...allTags]);
    const handleClearAll = () => onTagsChange([]);

    return (
        <div className="card" style={{ padding: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <h3 style={{ fontSize: 14, fontWeight: 700, margin: 0, color: t.text }}>Filter by Tags</h3>
                <div style={{ display: 'flex', gap: 8 }}>
                    <button
                        onClick={handleSelectAll}
                        style={{ background: 'transparent', border: `1px solid ${t.border}`, color: t.text, padding: '4px 8px', borderRadius: 4, fontSize: 11, cursor: 'pointer' }}
                    >
                        Select All
                    </button>
                    <button
                        onClick={handleClearAll}
                        style={{ background: 'transparent', border: `1px solid ${t.border}`, color: t.text, padding: '4px 8px', borderRadius: 4, fontSize: 11, cursor: 'pointer' }}
                    >
                        Clear All
                    </button>
                </div>
            </div>

            {/* Search Input */}
            <div style={{ position: 'relative', marginBottom: 16 }}>
                <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: t.dim }} />
                <input
                    type="text"
                    placeholder="Search tags..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    style={{
                        width: '100%', padding: '6px 30px', background: t.panel, border: `1px solid ${t.border}`,
                        borderRadius: 6, color: t.text, fontSize: 12, outline: 'none', boxSizing: 'border-box'
                    }}
                />
                {searchQuery && (
                    <button
                        onClick={() => setSearchQuery('')}
                        style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'transparent', border: 'none', color: t.dim, cursor: 'pointer' }}
                    >
                        <X size={14} />
                    </button>
                )}
            </div>

            {/* Selected Tags Summary */}
            {selectedTags.length > 0 && (
                <div style={{ marginBottom: 16, padding: 10, background: 'rgba(0, 230, 118, 0.05)', border: `1px solid rgba(0, 230, 118, 0.2)`, borderRadius: 6 }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                        <span style={{ fontSize: 11, fontWeight: 700, color: t.bull, textTransform: 'uppercase' }}>
                            Active Filters ({selectedTags.length})
                        </span>
                        <button onClick={handleClearAll} style={{ fontSize: 11, color: t.bull, background: 'transparent', border: 'none', cursor: 'pointer' }}>
                            Clear
                        </button>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                        {selectedTags.map(tag => (
                            <span
                                key={tag}
                                style={{
                                    display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 6px',
                                    borderRadius: 4, fontSize: 11, fontWeight: 600,
                                    background: (tagColors[tag] || t.border), color: t.text, border: `1px solid ${t.border}`
                                }}
                            >
                                {tag}
                                <button onClick={() => handleToggleTag(tag)} style={{ background: 'transparent', border: 'none', color: t.text, cursor: 'pointer', padding: 0 }}>
                                    <X size={10} />
                                </button>
                            </span>
                        ))}
                    </div>
                </div>
            )}

            {/* Tag List */}
            <div style={{ maxHeight: 300, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4 }}>
                {filteredTags.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '20px 0', color: t.dim, fontSize: 12 }}>
                        {searchQuery ? 'No tags match your search' : 'No tags available'}
                    </div>
                ) : (
                    filteredTags.map(tag => {
                        const isSelected = selectedTags.includes(tag);
                        return (
                            <button
                                key={tag}
                                onClick={() => handleToggleTag(tag)}
                                style={{
                                    display: 'flex', alignItems: 'center', gap: 10, padding: 8,
                                    borderRadius: 6, background: 'transparent', border: 'none', cursor: 'pointer',
                                    transition: 'background 0.1s'
                                }}
                                onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}
                                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                            >
                                <div style={{ color: isSelected ? t.bull : t.dim }}>
                                    {isSelected ? <CheckSquare size={16} /> : <Square size={16} />}
                                </div>
                                <span
                                    style={{
                                        flex: 1, textAlign: 'left', padding: '2px 8px', borderRadius: 4, fontWeight: 600, fontSize: 12,
                                        background: (tagColors[tag] || t.panel), color: t.text, border: `1px solid ${t.border}`
                                    }}
                                >
                                    {tag}
                                </span>
                            </button>
                        );
                    })
                )}
            </div>
        </div>
    );
};

export default TagFilter;
