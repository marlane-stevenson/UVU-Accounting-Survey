import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from statsmodels.stats.multicomp import pairwise_tukeyhsd
import os
import re

# Set style for plots
sns.set_theme(style="whitegrid")

def clean_filename(s):
    """Creates a filesystem-safe filename from a string."""
    keep = (" ", ".", "_")
    return "".join(c for c in s if c.isalnum() or c in keep).rstrip().replace(" ", "_")

def extract_likert_value(val):
    if pd.isna(val):
        return np.nan

    # Text-based agreement map
    agreement_map = {
        'Strongly Disagree': 1,
        'Disagree': 2,
        'Somewhat Disagree': 3,
        'Neither Agree nor Disagree': 4,
        'Somewhat Agree': 5,
        'Agree': 6,
        'Strongly Agree': 7
    }

    val_str = str(val).strip()

    if val_str in agreement_map:
        return agreement_map[val_str]

    # Check for "Number - Text" pattern (e.g., "1 - Strongly away...")
    # or just number strings "1", "2"
    # We look for the starting digit.
    if val_str and val_str[0].isdigit():
        # Check if it's a simple number 1-7
        if val_str.isdigit():
             d = int(val_str)
             if 1 <= d <= 7:
                 return d
        # Check pattern "Digit - ..." or "Digit"
        # Regex is safer
        match = re.match(r'^([1-7])(\s*-.*)?$', val_str)
        if match:
            return int(match.group(1))

    # Check float
    if isinstance(val, (int, float)):
        if 1 <= val <= 7:
            return int(val)

    return np.nan

def analyze_survey():
    print("Loading data...")
    try:
        df = pd.read_excel('data/data.xlsx')
    except Exception as e:
        print(f"Error loading data: {e}")
        return

    # Identify Likert columns
    likert_cols = []

    print("Identifying Likert columns...")
    for col in df.columns:
        unique_vals = df[col].dropna().unique()
        if len(unique_vals) == 0:
            continue

        # Check if it contains known Likert text
        has_agreement = any(v in ['Strongly Agree', 'Strongly Disagree'] for v in unique_vals)

        # Check if it contains "1 - ..." and "7 - ..." pattern
        has_anchors = any(str(v).startswith('1 - ') for v in unique_vals) and \
                      any(str(v).startswith('7 - ') for v in unique_vals)

        # Check if values are mostly 1-7 integers (or strings of them)
        # This is riskier, so we rely on anchors or explicit agreement text for now
        # unless we want to be very aggressive.
        # Given the dataset inspection, the non-agreement questions seem to ALL have the "1 - ..." / "7 - ..." format
        # or at least one of them?
        # Let's check for at least one anchor "X - ..." where X is 1 or 7.
        has_one_anchor = any(str(v).startswith('1 - ') or str(v).startswith('7 - ') for v in unique_vals)

        if has_agreement or has_one_anchor:
            print(f"Processing Likert column: {col}")
            # Map the column
            df[col] = df[col].apply(extract_likert_value)
            df[col] = pd.to_numeric(df[col], errors='coerce')
            likert_cols.append(col)

    print(f"Found {len(likert_cols)} Likert columns.")

    # Define cohorts
    # Update column names based on inspection
    course_col = 'Which class are you taking this survey for?'
    major_col = 'What is your primary major? - Selected Choice'

    if course_col not in df.columns:
        print(f"Error: Course column '{course_col}' not found.")
        print(f"Available columns: {df.columns.tolist()}")
        return

    if major_col not in df.columns:
        print(f"Error: Major column '{major_col}' not found.")
        return

    cohorts = {
        'Total Population': df,
        'Accounting Majors': df[df[major_col] == 'Accounting']
    }

    output_path = 'outputs/summary_analysis.md'
    os.makedirs('outputs/plots', exist_ok=True)

    with open(output_path, 'w') as f:
        f.write("# UVU Accounting Survey Analysis\n\n")

        for cohort_name, cohort_df in cohorts.items():
            f.write(f"## {cohort_name}\n\n")
            print(f"Analyzing {cohort_name}...")

            if cohort_df.empty:
                f.write("No data available for this cohort.\n\n")
                continue

            for col in likert_cols:
                # Calculate valid count
                valid_count = cohort_df[col].count()
                if valid_count == 0:
                    continue

                f.write(f"### Question: {col}\n\n")

                # Descriptive Stats
                desc = cohort_df[col].describe()
                f.write(f"**Overall Statistics:**\n")
                f.write(f"- Count: {desc['count']:.0f}\n")
                f.write(f"- Mean: {desc['mean']:.2f}\n")
                f.write(f"- Std Dev: {desc['std']:.2f}\n\n")

                # Group by Course
                f.write("**Statistics by Course:**\n\n")
                course_stats = cohort_df.groupby(course_col)[col].describe()
                # Select only relevant columns
                display_stats = course_stats[['count', 'mean', 'std']]
                f.write(display_stats.to_markdown())
                f.write("\n\n")

                # ANOVA
                groups = []
                course_names = []
                for course, group_df in cohort_df.groupby(course_col):
                    vals = group_df[col].dropna()
                    if len(vals) > 1: # Need at least 2 values for variance
                        groups.append(vals)
                        course_names.append(course)

                if len(groups) > 1:
                    try:
                        f_val, p_val = stats.f_oneway(*groups)
                        f.write(f"**One-Way ANOVA:**\n")
                        f.write(f"- F-statistic: {f_val:.4f}\n")
                        f.write(f"- p-value: {p_val:.4f}\n")

                        if p_val < 0.05:
                            f.write("\n**Result:** Significant difference found (p < 0.05). Performing Tukey HSD.\n\n")

                            tukey_data = cohort_df[[course_col, col]].dropna()
                            # Ensure we only check groups present in data
                            tukey = pairwise_tukeyhsd(endog=tukey_data[col], groups=tukey_data[course_col], alpha=0.05)
                            f.write(str(tukey.summary()))
                            f.write("\n\n")
                        else:
                            f.write("\n**Result:** No significant difference found (p >= 0.05).\n\n")
                    except Exception as e:
                        f.write(f"Error in ANOVA: {e}\n\n")
                else:
                    f.write("Not enough groups/data for ANOVA.\n\n")

                # Visualization
                try:
                    plt.figure(figsize=(10, 6))
                    sns.boxplot(x=course_col, y=col, data=cohort_df)
                    plt.title(f'{cohort_name}: {col[:50]}...') # Truncate long titles
                    plt.xticks(rotation=45)
                    plt.tight_layout()

                    # Save plot
                    plot_filename = f"{clean_filename(cohort_name)}_{clean_filename(col[:30])}_{np.random.randint(1000)}.png"
                    plot_path = os.path.join('outputs/plots', plot_filename)
                    plt.savefig(plot_path)
                    plt.close()

                    f.write(f"![Boxplot]({os.path.join('plots', plot_filename)})\n\n")
                    f.write("---\n\n")
                except Exception as e:
                    print(f"Error plotting {col}: {e}")

    print(f"Analysis complete. Results saved to {output_path}")

if __name__ == "__main__":
    analyze_survey()
