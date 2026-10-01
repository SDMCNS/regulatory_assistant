/**
 * Client-side text similarity search and highlighting engine for regulatory documents.
 * 
 * Computes multi-factor relevance scores combining:
 * 1. BM25 / TF-IDF term weighting (giving higher weight to unique domain terms)
 * 2. Exact phrase bonus (when multiple words appear in sequence)
 * 3. Title match boost (matches in section titles/codes like CS 22.1)
 * 4. Query term coverage (percentage of query words found)
 * 5. Safe HTML highlighting of matched keywords
 */

import { DocSection } from '../types';

export interface SectionSimilarityResult {
  sectionId: string;
  score: number;            // 0 to 100 percentage
  matchCount: number;       // total occurrences of query terms
  matchedTerms: string[];   // terms from query that were found
  hasExactPhrase: boolean;
  hasTitleMatch: boolean;
  isMatch: boolean;
}

const STOPWORDS = new Set([
  'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
  'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the',
  'to', 'was', 'were', 'will', 'with', 'or', 'such', 'this', 'any',
  'shall', 'must', 'each', 'all', 'may', 'under', 'into'
]);

/**
 * Tokenize a string into cleaned lower-case words
 */
export function tokenizeText(text: string): string[] {
  if (!text) return [];
  // Strip markdown formatting symbols
  const stripped = text
    .replace(/[#*_`\[\]()><!~\\-]/g, ' ')
    .replace(/\s+/g, ' ')
    .toLowerCase();

  return stripped
    .split(/[^a-z0-9_]+/)
    .filter(w => w.length >= 2);
}

/**
 * Computes Inverse Document Frequency (IDF) for all unique terms across the document's sections.
 */
function computeCorpusIDF(sections: DocSection[]): Map<string, number> {
  const docFreq = new Map<string, number>();
  const N = sections.length;

  for (const sec of sections) {
    const tokens = new Set(tokenizeText(`${sec.title} ${sec.markdown}`));
    for (const t of tokens) {
      docFreq.set(t, (docFreq.get(t) || 0) + 1);
    }
  }

  const idfMap = new Map<string, number>();
  for (const [term, df] of docFreq.entries()) {
    // Standard BM25 IDF formulation: log(1 + (N - df + 0.5) / (df + 0.5))
    const idf = Math.log(1 + (N - df + 0.5) / (df + 0.5));
    idfMap.set(term, Math.max(0.2, idf));
  }

  return idfMap;
}

/**
 * Calculates similarity scores for all sections in a document against a user query.
 */
export function calculateDocumentSimilarity(
  query: string,
  sections: DocSection[],
  minScoreThreshold = 10
): Map<string, SectionSimilarityResult> {
  const results = new Map<string, SectionSimilarityResult>();
  if (!query || !query.trim() || sections.length === 0) {
    return results;
  }

  const cleanQuery = query.trim().toLowerCase();
  const queryTokens = tokenizeText(cleanQuery);
  const significantTokens = queryTokens.filter(t => !STOPWORDS.has(t));
  const tokensToSearch = significantTokens.length > 0 ? significantTokens : queryTokens;

  if (tokensToSearch.length === 0) {
    return results;
  }

  const idfMap = computeCorpusIDF(sections);
  const avgDocLength = sections.reduce((sum, s) => sum + s.wordCount, 0) / (sections.length || 1);

  // Maximum potential theoretical score for normalization
  let maxTheoreticalScore = 0;
  for (const t of tokensToSearch) {
    maxTheoreticalScore += (idfMap.get(t) || 1.0) * 3.0; // term weight + bonuses
  }
  maxTheoreticalScore = Math.max(1.0, maxTheoreticalScore);

  let highestObservedScore = 0.001;
  const rawScores: { id: string; raw: number; res: SectionSimilarityResult }[] = [];

  for (const sec of sections) {
    const titleLower = sec.title.toLowerCase();
    const bodyLower = sec.markdown.toLowerCase();
    const secTokens = tokenizeText(`${sec.title} ${sec.markdown}`);
    const secDocLength = sec.wordCount || secTokens.length || 1;

    // Count term frequencies in this section
    const termCounts = new Map<string, number>();
    for (const t of secTokens) {
      termCounts.set(t, (termCounts.get(t) || 0) + 1);
    }

    let rawScore = 0;
    const matchedTerms: string[] = [];
    let matchCount = 0;

    for (const qToken of tokensToSearch) {
      let count = termCounts.get(qToken) || 0;

      // Substring / prefix fuzzy match if exact word didn't hit
      if (count === 0 && qToken.length >= 4) {
        for (const [secToken, secCount] of termCounts.entries()) {
          if (secToken.includes(qToken) || qToken.includes(secToken)) {
            count += secCount * 0.75;
          }
        }
      }

      if (count > 0) {
        matchedTerms.push(qToken);
        matchCount += Math.floor(count);

        const idf = idfMap.get(qToken) || 1.0;
        // BM25 TF formula: (count * (k1 + 1)) / (count + k1 * (1 - b + b * (docLen / avgLen)))
        // with k1 = 1.2, b = 0.75
        const tf = (count * 2.2) / (count + 1.2 * (0.25 + 0.75 * (secDocLength / avgDocLength)));
        rawScore += idf * tf;
      }
    }

    // Exact Phrase Bonus
    const hasExactPhrase = cleanQuery.length > 3 && (
      titleLower.includes(cleanQuery) || bodyLower.includes(cleanQuery)
    );
    if (hasExactPhrase) {
      rawScore += 4.0;
    }

    // Title Match Bonus (title mentions query token)
    const hasTitleMatch = tokensToSearch.some(t => titleLower.includes(t));
    if (hasTitleMatch) {
      rawScore += 2.5;
    }

    // Term Coverage Bonus (how many query words were present in this section)
    const coverageRatio = matchedTerms.length / (tokensToSearch.length || 1);
    rawScore *= (0.5 + 0.5 * coverageRatio);

    if (rawScore > highestObservedScore) {
      highestObservedScore = rawScore;
    }

    rawScores.push({
      id: sec.id,
      raw: rawScore,
      res: {
        sectionId: sec.id,
        score: 0,
        matchCount,
        matchedTerms,
        hasExactPhrase,
        hasTitleMatch,
        isMatch: false,
      }
    });
  }

  // Normalize scores to percentage (0 - 100)
  for (const item of rawScores) {
    if (item.raw <= 0) {
      results.set(item.id, item.res);
      continue;
    }

    // Relative scoring against highest score and max theoretical
    const relativeScore = (item.raw / highestObservedScore) * 100;
    const finalScore = Math.min(100, Math.round(relativeScore));

    item.res.score = finalScore;
    item.res.isMatch = finalScore >= minScoreThreshold && item.res.matchedTerms.length > 0;
    results.set(item.id, item.res);
  }

  return results;
}

/**
 * Safely highlights matching query terms in rendered HTML without corrupting tags.
 */
export function highlightHtmlContent(html: string, query: string): string {
  if (!query || !query.trim() || !html) {
    return html;
  }

  const queryTokens = tokenizeText(query);
  const significantTokens = queryTokens.filter(t => !STOPWORDS.has(t) && t.length >= 2);
  const terms = significantTokens.length > 0 ? significantTokens : queryTokens.filter(t => t.length >= 2);

  if (terms.length === 0) {
    return html;
  }

  // Sort terms by length descending so longer phrases match before sub-words
  const sortedTerms = Array.from(new Set(terms)).sort((a, b) => b.length - a.length);
  const escapedTerms = sortedTerms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  
  // Word boundary regex for term matching
  const termRegex = new RegExp(`\\b(${escapedTerms.join('|')})`, 'gi');

  // Regex: match tags (<[^>]+>) or text outside tags ([^<]+)
  return html.replace(/(<[^>]+>)|([^<]+)/g, (_match, tag, text) => {
    if (tag) return tag; // Return HTML tag untouched
    if (!text) return '';
    return text.replace(
      termRegex,
      '<mark class="bg-amber-400/30 text-amber-200 border-b-2 border-amber-400 font-semibold px-1 py-0.5 rounded shadow-sm">$1</mark>'
    );
  });
}
