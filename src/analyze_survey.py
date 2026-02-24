import pandas as pd
import numpy as np
import scipy.stats as stats
from statsmodels.stats.multicomp import pairwise_tukeyhsd
import seaborn as sns
import matplotlib.pyplot as plt
import os
import re

# Set up paths
DATA_PATH = 'data/data.xlsx'
OUTPUT_DIR = 'outputs'
PLOTS_DIR = os.path.join(OUTPUT_DIR, 'plots')
SUMMARY_FILE = os.path.join(OUTPUT_DIR, 'summary_analysis.md')

# Ensure directories exist
os.makedirs(PLOTS_DIR, exist_ok=True)

def extract_likert_value(val):
    """
    Extracts numerical value from Likert scale text (e.g., '7 - Strongly agree' -> 7).
    Returns NaN if extraction fails.
    """
    if pd.isna(val):
        return np.nan
    if isinstance(val, (int, float)):
        return float(val)

    val_str = str(val).strip()
    match = re.match(r'^(\d+)', val_str)
    if match:
        return float(match.group(1))
    return np.nan

def load_and_preprocess_data():
    """
    Loads data, extracts question text, cleans Likert columns, and returns cleaned dataframe and question map.
    """
    print("Loading data...")
    df = pd.read_excel(DATA_PATH, header=0)

    # Extract question text from the first row (index 0)
    question_map = {}
    for col in df.columns:
        question_map[col] = str(df[col].iloc[0]).strip()

    # Drop the description row (index 0) to get data rows
    data_df = df.iloc[1:].copy()

    # Identify Likert columns
    # Based on inspection: Q12_*, Q15_*, Q18_*, Q17, Q22, Q23, Q24, Q32, Q31 (col 67)
    # Note: Q31 appears twice. We need the one that is a Likert scale.
    # We can check the question text to differentiate.
    likert_cols = []

    # Explicit list of Likert-like question bases
    likert_bases = ['Q12', 'Q15', 'Q18']
    single_likert_cols = ['Q17', 'Q22', 'Q23', 'Q24', 'Q32']

    # Add matrix questions (Q12_1, Q12_2, etc.)
    for col in data_df.columns:
        for base in likert_bases:
            if col.startswith(base + '_'):
                likert_cols.append(col)

    # Add single Likert questions
    for col in single_likert_cols:
        if col in data_df.columns:
            likert_cols.append(col)

    # Handle Q31 duplicate
    # We want "To what degree do you like accounting principles and rules?"
    # Find columns starting with Q31
    q31_cols = [c for c in data_df.columns if str(c).startswith('Q31')]
    for col in q31_cols:
        q_text = question_map.get(col, "")
        if "principles and rules" in q_text:
            likert_cols.append(col)

    print(f"Identified {len(likert_cols)} Likert scale questions.")

    # Convert Likert columns to numeric
    for col in likert_cols:
        data_df[col] = data_df[col].apply(extract_likert_value)

    # Ensure grouping columns are clean
    # Q2 is Course
    if 'Q2' in data_df.columns:
        data_df = data_df.dropna(subset=['Q2']) # Drop rows with no course

    # Q7 is Major

    return data_df, question_map, likert_cols

def analyze_segment(df, segment_name, likert_cols, question_map, summary_lines):
    """
    Analyzes a data segment (e.g., "All Data", "Accounting Majors").
    Performs ANOVA and Tukey for each Likert question across 'Q2' (Course).
    Generates plots and appends to summary.
    """
    print(f"\nAnalyzing segment: {segment_name}")
    summary_lines.append(f"## Analysis Segment: {segment_name}\n")

    # Check if we have data
    if df.empty:
        summary_lines.append("No data available for this segment.\n")
        return

    courses = df['Q2'].unique()
    summary_lines.append(f"**Number of observations:** {len(df)}\n")
    summary_lines.append(f"**Courses included:** {', '.join(map(str, courses))}\n")

    for col in likert_cols:
        q_text = question_map.get(col, col)
        # Simplify question text for plot title (remove leading generic text if present)
        # e.g. "How strongly... - Detail oriented" -> "Detail oriented"
        short_q_text = q_text.split('-')[-1].strip()
        if len(short_q_text) > 50:
             short_q_text = short_q_text[:50] + "..."

        # Drop NaNs for this specific column
        valid_data = df.dropna(subset=[col, 'Q2'])

        if valid_data.empty:
            continue

        # Group by course
        groups = [valid_data[valid_data['Q2'] == course][col] for course in courses]
        # Filter out empty groups (some courses might not have answered this question)
        groups = [g for g in groups if len(g) > 1] # Need >1 for variance

        if len(groups) < 2:
            # summary_lines.append(f"### {col}: {short_q_text}\n")
            # summary_lines.append("Not enough groups for ANOVA.\n")
            continue

        # Perform ANOVA
        f_stat, p_val = stats.f_oneway(*groups)

        summary_lines.append(f"### {col}: {short_q_text}\n")
        summary_lines.append(f"- **Question Text:** {q_text}\n")
        summary_lines.append(f"- **ANOVA:** F={f_stat:.4f}, p={p_val:.4f}\n")

        # Descriptive stats table
        desc_stats = valid_data.groupby('Q2')[col].agg(['mean', 'std', 'count']).round(2)
        summary_lines.append("\n**Descriptive Statistics:**\n")
        summary_lines.append(desc_stats.to_markdown() + "\n")

        if p_val < 0.05:
            summary_lines.append("\n**Significant Difference Detected (p < 0.05).**\n")
            try:
                tukey = pairwise_tukeyhsd(endog=valid_data[col], groups=valid_data['Q2'], alpha=0.05)
                summary_lines.append("\n**Tukey HSD Post-hoc Results:**\n")
                # Filter for only true rejections to keep it concise
                tukey_df = pd.DataFrame(data=tukey.summary().data[1:], columns=tukey.summary().data[0])
                sig_diffs = tukey_df[tukey_df['reject'] == True]

                if not sig_diffs.empty:
                    summary_lines.append(sig_diffs.to_markdown(index=False) + "\n")
                else:
                    summary_lines.append("No pairwise differences were significant according to Tukey HSD.\n")
            except Exception as e:
                summary_lines.append(f"Error performing Tukey HSD: {e}\n")
        else:
            summary_lines.append("\nNo significant difference across courses.\n")

        # Generate Boxplot
        plt.figure(figsize=(10, 6))
        sns.boxplot(x='Q2', y=col, data=valid_data)
        plt.title(f"{segment_name}: {short_q_text}")
        plt.xlabel("Course")
        plt.ylabel("Likert Score (1-7)")
        plt.xticks(rotation=45)
        plt.tight_layout()

        # Save plot
        plot_filename = f"{segment_name.replace(' ', '_')}_{col}.png"
        # Sanitize filename
        plot_filename = re.sub(r'[^\w\-_.]', '', plot_filename)
        plot_path = os.path.join(PLOTS_DIR, plot_filename)
        plt.savefig(plot_path)
        plt.close()

        summary_lines.append(f"\n![Boxplot for {col}](plots/{plot_filename})\n")
        summary_lines.append("---\n")

def main():
    # Load data
    df, question_map, likert_cols = load_and_preprocess_data()

    summary_lines = ["# Survey Analysis Report\n"]
    summary_lines.append("Analysis of UVU accounting student survey data.\n")

    # 1. Analyze Total Population
    analyze_segment(df, "All Students", likert_cols, question_map, summary_lines)

    # 2. Analyze Accounting Majors Only
    # Filter Q7 == 'Accounting'
    # Note: Check exact string in data
    # From inspection: 'Accounting' is a value.
    if 'Q7' in df.columns:
        acct_majors_df = df[df['Q7'] == 'Accounting']
        analyze_segment(acct_majors_df, "Accounting Majors", likert_cols, question_map, summary_lines)
    else:
        summary_lines.append("\n## Accounting Majors Analysis\n")
        summary_lines.append("Could not find Major column (Q7) to filter.\n")

    # Write summary to file
    with open(SUMMARY_FILE, 'w') as f:
        f.writelines(summary_lines)

    print(f"Analysis complete. Summary saved to {SUMMARY_FILE}")

if __name__ == "__main__":
    main()
