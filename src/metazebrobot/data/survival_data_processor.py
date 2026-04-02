"""
Survival data processor for MetaZebrobot.

This module provides functions for processing and cleaning survival data
before export to CSV files using Polars for high performance.
"""

import logging
import polars as pl
import numpy as np
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)

def convert_date_columns(df: pl.DataFrame) -> pl.DataFrame:
    """
    Converts specified date columns (YYYYMMDD) to Date type in Polars.
    Handles potential nulls or zeros/empty strings.
    """
    logger.info("Converting date columns (YYYYMMDD -> Date)...")
    date_cols_to_convert = ['date_fertilized', 'date_created', 'check_date', 'termination_date']

    conversion_exprs = []
    found_cols_count = 0
    cols_missing = []
    try:
        # Check if columns exist before attempting conversion
        available_cols = [col for col in date_cols_to_convert if col in df.columns]
        cols_missing = [col for col in date_cols_to_convert if col not in df.columns]

        if cols_missing:
            logger.warning(f"Columns not found for date conversion: {', '.join(cols_missing)}")

        if not available_cols:
            logger.warning("No date columns found or specified for conversion.")
            return df

        logger.info(f"Applying conversion to {len(available_cols)} date column(s).")

        for col_name in available_cols:
            # Ensure the column is Utf8 before string operations/parsing
            # This helps if the schema inference wasn't perfect or if data types changed unexpectedly
            df = df.with_columns(pl.col(col_name).cast(pl.Utf8, strict=False))

            conversion_exprs.append(
                pl.when(pl.col(col_name).is_null() | (pl.col(col_name) == "0") | (pl.col(col_name) == ""))
                .then(pl.lit(None, dtype=pl.Date))
                .otherwise(
                    pl.col(col_name)
                    .str.strptime(pl.Date, format="%Y%m%d", strict=False, exact=True) # Use exact=True for better parsing
                )
                .alias(col_name)
            )

        # Execute the conversion expressions together
        return df.with_columns(conversion_exprs)

    except Exception as e:
        logger.error(f"Error applying date conversion expressions: {e}", exc_info=True)
        # Return original DataFrame if conversion fails
        return df

def calculate_survival_derivatives(df: pl.DataFrame) -> pl.DataFrame:
    """
    Calculates the day-to-day change in survival rate per dish_id using Polars window functions.

    Parameters:
    -----------
    df : pl.DataFrame
        Input DataFrame with dish_id, days_since_fertilization, survival_rate columns.

    Returns:
    --------
    pl.DataFrame
        DataFrame with an added 'survival_rate_change' column.
    """
    logger.info("Calculating survival rate derivatives...")

    required_cols = ['dish_id', 'days_since_fertilization', 'survival_rate']
    if not all(col in df.columns for col in required_cols):
        missing = [col for col in required_cols if col not in df.columns]
        logger.error(f"Missing required columns for derivative calculation: {missing}")
        # Ensure the column is added, even if null, to maintain schema consistency
        return df.with_columns(pl.lit(None, dtype=pl.Float64).alias('survival_rate_change'))

    try:
        # Ensure types are correct before calculation
        df_casted = df.with_columns([
            pl.col('days_since_fertilization').cast(pl.Float64, strict=False),
            pl.col('survival_rate').cast(pl.Float64, strict=False)
        ])

        lazy_df = df_casted.lazy()
        result_lf = lazy_df.sort('dish_id', 'days_since_fertilization').with_columns(
            pl.col('survival_rate').shift(1).over('dish_id').alias('prev_survival_rate'),
            pl.col('days_since_fertilization').shift(1).over('dish_id').alias('prev_days')
        ).with_columns(
            pl.when(
                pl.col('prev_days').is_not_null() &
                (pl.col('days_since_fertilization') > pl.col('prev_days')) # Comparison should work fine with floats
             )
            .then(
                # Calculate change, handle division by zero (though day diff should > 0)
                pl.when(pl.col('days_since_fertilization') != pl.col('prev_days'))
                .then(
                    (pl.col('survival_rate') - pl.col('prev_survival_rate')) /
                    (pl.col('days_since_fertilization') - pl.col('prev_days'))
                 )
                 .otherwise(None) # Avoid division by zero if days are somehow the same
            )
            .otherwise(None) # No change if prev_days is null
            .alias('survival_rate_change')
        ).drop(['prev_survival_rate', 'prev_days'])

        logger.info("Collecting derivative results...")
        result_df = result_lf.collect()
        logger.info("Derivative calculation complete.")
        return result_df
    except Exception as e:
        logger.error(f"Error during derivative calculation/collection: {e}", exc_info=True) # Add exc_info
        # Return original df but add the column as null to avoid schema issues later
        return df.with_columns(pl.lit(None, dtype=pl.Float64).alias('survival_rate_change'))

def calculate_density_metrics(df: pl.DataFrame) -> pl.DataFrame:
    """
    Calculate fish density metrics and categorize based on volume per fish using Polars.
    """
    logger.info("Calculating density metrics...")

    required_cols = ['initial_count', 'vol_water_total']
    cols_to_add = {} # Dictionary to hold columns to add if inputs are missing

    if 'initial_count' not in df.columns:
        logger.warning("Missing 'initial_count' column for density calculation. Adding null column.")
        cols_to_add['initial_count'] = pl.lit(None, dtype=pl.Float64)
    if 'vol_water_total' not in df.columns:
        logger.warning("Missing 'vol_water_total' column for density calculation. Adding null column.")
        cols_to_add['vol_water_total'] = pl.lit(None, dtype=pl.Float64)

    # Add missing columns if any
    if cols_to_add:
        df = df.with_columns(**cols_to_add)

    # Ensure input columns are numeric Float64 and handle nulls BEFORE division
    df_processed = df.with_columns([
        pl.col('initial_count').cast(pl.Float64, strict=False).fill_null(0.0).alias('initial_count_num'),
        pl.col('vol_water_total').cast(pl.Float64, strict=False).fill_null(0.0).alias('vol_water_total_num')
    ])

    # Now calculate densities using the cleaned numeric columns
    df_processed = df_processed.with_columns([
        pl.when(pl.col('vol_water_total_num') != 0.0) # Check vol != 0 before division
        .then(pl.col('initial_count_num') / pl.col('vol_water_total_num'))
        .otherwise(None) # Avoid division by zero -> null density
        .alias('fish_density'),

        pl.when(pl.col('initial_count_num') > 0.0) # Check count > 0 before division
        .then(pl.col('vol_water_total_num') / pl.col('initial_count_num'))
        .otherwise(None) # Avoid division by zero -> null volume/fish
        .alias('volume_per_fish')
    ])

    # Categorize based on volume_per_fish
    df_processed = df_processed.with_columns(
        pl.when(pl.col('volume_per_fish').is_null())
        .then(pl.lit(None, dtype=pl.Categorical)) # Ensure null is Categorical if others are
        .when(pl.col('volume_per_fish') <= 2.0) # Use float literals
        .then(pl.lit('Very High (<2mL/fish)'))
        .when(pl.col('volume_per_fish') <= 3.0)
        .then(pl.lit('High (2-3mL/fish)'))
        .when(pl.col('volume_per_fish') <= 4.0)
        .then(pl.lit('Medium (3-4mL/fish)'))
        .otherwise(pl.lit('Low (>4mL/fish)')) # Catches volume_per_fish > 4.0
        .cast(pl.Categorical) # Cast the final result to Categorical
        .alias('density_category')
    )

    # Drop temporary columns and return
    return df_processed.drop(['initial_count_num', 'vol_water_total_num'])

def process_survival_data(df: pl.DataFrame) -> pl.DataFrame:
    """
    Process survival data by applying all transformation steps. Includes detailed error handling.
    """
    logger.info("Processing survival data...")
    if df is None or df.height == 0:
         logger.warning("Input DataFrame is empty. Skipping processing.")
         return df # Return the empty/None DataFrame

    df_current_step = df # Start with the input df

    # --- Step 1: Date Conversion ---
    try:
        logger.info("Step 1: Converting date columns...")
        df_current_step = convert_date_columns(df_current_step)
        logger.info("Step 1: Date conversion complete.")
        if df_current_step is None or df_current_step.height == 0:
             logger.warning("DataFrame empty after date conversion.")
             return df_current_step
        # Optional: Log schema after conversion
        # logger.info(f"Schema after date conversion:\n{df_current_step.schema}")
    except Exception as e:
        logger.error(f"ERROR during date conversion step: {e}", exc_info=True)
        return df # Return original df if this step fails

    # --- Intermediate Step: Calculate Survival Metrics --- <<<<------ NEW BLOCK ------>>>>
    try:
        logger.info("Intermediate Step: Calculating survival metrics (days_since_fertilization, survival_rate, etc.)...")
        # Ensure required date columns are present and are Date type after conversion
        required_date_cols = ['date_fertilized', 'check_date']
        if not all(col in df_current_step.columns for col in required_date_cols):
             missing_cols = [col for col in required_date_cols if col not in df_current_step.columns]
             logger.error(f"Missing required date columns for survival metric calculation: {missing_cols}")
             return df_current_step # Return partially processed df

        # Check types AFTER conversion
        if df_current_step['date_fertilized'].dtype != pl.Date or df_current_step['check_date'].dtype != pl.Date:
            logger.error(f"Date columns (date_fertilized: {df_current_step['date_fertilized'].dtype}, check_date: {df_current_step['check_date'].dtype}) are not Date type before calculating days_since_fertilization.")
            # Handle error - perhaps return or try casting again if appropriate
            return df_current_step # Return partially processed df

        # Calculate days since fertilization using .dt accessor now that types are Date
        df_current_step = df_current_step.with_columns(
            (pl.col('check_date') - pl.col('date_fertilized')).dt.total_days().alias('days_since_fertilization')
        )

        # Calculate cumulative deaths and survival rate
        required_survival_cols = ['dish_id', 'fish_deaths', 'initial_count']
        if all(col in df_current_step.columns for col in required_survival_cols):
            # Ensure types are numeric and handle potential nulls before calculations
            df_current_step = df_current_step.with_columns([
                pl.col('initial_count').cast(pl.Int64, strict=False).fill_null(0),
                pl.col('fish_deaths').cast(pl.Int64, strict=False).fill_null(0)
            ])

            # Sort by the now-converted check_date for window functions (important!)
            # Check if check_date is sortable (not all null) after conversion
            if df_current_step.select(pl.col('check_date').is_null().all()).item():
                 logger.error("Cannot sort by check_date for cumulative sum as all values are null.")
                 # Handle error: add null columns for subsequent steps
                 df_current_step = df_current_step.with_columns([
                     pl.lit(None, dtype=pl.Int64).alias('cumulative_deaths'),
                     pl.lit(None, dtype=pl.Int64).alias('remaining'),
                     pl.lit(None, dtype=pl.Float64).alias('survival_rate')
                 ])
            else:
                 # Ensure check_date is sorted correctly now that it's a Date type
                 df_current_step = df_current_step.sort(['dish_id', 'check_date'])

                 # Calculate cumulative deaths using Polars window function
                 df_current_step = df_current_step.with_columns(
                     pl.col('fish_deaths').cum_sum().over('dish_id').alias('cumulative_deaths')
                 )

                 # Calculate remaining fish
                 df_current_step = df_current_step.with_columns(
                     (pl.col('initial_count') - pl.col('cumulative_deaths')).clip(lower_bound=0).alias('remaining') # Use clip_min for safety
                 )

                 # Calculate survival rate
                 df_current_step = df_current_step.with_columns(
                     pl.when(pl.col('initial_count') > 0)
                     .then((pl.col('remaining').cast(pl.Float64) / pl.col('initial_count').cast(pl.Float64)) * 100.0) # Cast to float for division
                     .otherwise(None) # Or 0.0 if initial_count is 0
                     .alias('survival_rate')
                 )
        else:
             missing_survival_cols = [col for col in required_survival_cols if col not in df_current_step.columns]
             logger.warning(f"Missing columns required for cumulative death/survival rate calculation: {missing_survival_cols}. Skipping these calculations.")
             # Add null columns if they don't exist to prevent schema issues later
             cols_to_add_null = {}
             if 'cumulative_deaths' not in df_current_step.columns: cols_to_add_null['cumulative_deaths'] = pl.lit(None, dtype=pl.Int64)
             if 'remaining' not in df_current_step.columns: cols_to_add_null['remaining'] = pl.lit(None, dtype=pl.Int64)
             if 'survival_rate' not in df_current_step.columns: cols_to_add_null['survival_rate'] = pl.lit(None, dtype=pl.Float64)
             if cols_to_add_null:
                 df_current_step = df_current_step.with_columns(**cols_to_add_null)


        logger.info("Intermediate Step: Survival metrics calculation complete.")
        if df_current_step is None or df_current_step.height == 0:
             logger.warning("DataFrame empty after survival metrics calculation.")
             return df_current_step
        # Optional: Log schema after this step
        # logger.info(f"Schema after survival metrics:\n{df_current_step.schema}")

    except Exception as e:
        logger.error(f"ERROR during survival metrics calculation step: {e}", exc_info=True)
        # Decide how to handle: return partially processed df or original df
        return df_current_step # Return df as it was before this failed step

    # --- Step 2: Density Metrics --- (Existing block)
    try:
        logger.info("Step 2: Calculating density metrics...")
        df_current_step = calculate_density_metrics(df_current_step)
        logger.info("Step 2: Density metrics calculation complete.")
        if df_current_step is None or df_current_step.height == 0:
             logger.warning("DataFrame empty after density metrics.")
             return df_current_step
    except Exception as e:
        logger.error(f"ERROR during density metrics calculation step: {e}", exc_info=True)
        return df_current_step # Return df as it was before this failed step

    # --- Step 3: Survival Derivatives --- (Existing block)
    try:
        logger.info("Step 3: Calculating survival derivatives...")
        df_current_step = calculate_survival_derivatives(df_current_step)
        logger.info("Step 3: Survival derivatives calculation complete.")
        if df_current_step is None or df_current_step.height == 0:
             logger.warning("DataFrame empty after survival derivatives.")
             return df_current_step
    except Exception as e:
        logger.error(f"ERROR during survival derivatives calculation step: {e}", exc_info=True)
        return df_current_step # Return df as it was before this failed step

    # --- Processing Complete ---
    logger.info("Data processing complete")
    return df_current_step # Return the fully processed df

def create_survival_summary(df: pl.DataFrame) -> pl.DataFrame:
    """
    Create a summary DataFrame with aggregated statistics by genotype.

    Parameters:
    -----------
    df : pl.DataFrame
        Processed survival data. Should contain 'dish_id', 'genotype',
        'days_since_fertilization', 'survival_rate'.

    Returns:
    --------
    pl.DataFrame
        Summary DataFrame with statistics by genotype. Returns empty DataFrame on error
        or if required columns are missing.
    """
    logger.info("Creating survival summary...")

    required_cols = ['dish_id', 'genotype', 'days_since_fertilization', 'survival_rate']
    if not all(col in df.columns for col in required_cols):
        missing = [col for col in required_cols if col not in df.columns]
        logger.error(f"Missing required columns for summary creation: {missing}. Cannot create summary.")
        # Return empty DataFrame with expected columns if possible, or just empty
        return pl.DataFrame({
            'genotype': [], 'count': [], 'mean_survival': [], 'median_survival': [],
            'min_survival': [], 'max_survival': [], 'std_survival': []
        }, schema={ # Define schema for empty df
            'genotype': pl.Utf8, 'count': pl.UInt32, 'mean_survival': pl.Float64,
            'median_survival': pl.Float64, 'min_survival': pl.Float64,
            'max_survival': pl.Float64, 'std_survival': pl.Float64
        })


    try:
        # Ensure days_since_fertilization is numeric for max aggregation
        df = df.with_columns(pl.col('days_since_fertilization').cast(pl.Int64, strict=False))

        # Get latest measurement for each dish
        # Use filter combined with a window function for efficiency
        latest_records = df.filter(
            pl.col('days_since_fertilization') == pl.max('days_since_fertilization').over('dish_id')
        )

        # Create summary statistics by genotype
        # Ensure survival_rate is float for aggregations
        latest_records = latest_records.with_columns(pl.col('survival_rate').cast(pl.Float64, strict=False))

        summary = latest_records.group_by('genotype').agg([
            pl.n_unique('dish_id').alias('count'),
            pl.mean('survival_rate').alias('mean_survival'),
            pl.median('survival_rate').alias('median_survival'),
            pl.min('survival_rate').alias('min_survival'),
            pl.max('survival_rate').alias('max_survival'),
            pl.std('survival_rate').alias('std_survival')
        ])

        # Add additional data if columns exist
        if 'volume_per_fish' in latest_records.columns:
             # Ensure volume_per_fish is float for aggregations
            latest_records = latest_records.with_columns(pl.col('volume_per_fish').cast(pl.Float64, strict=False))
            volume_stats = latest_records.group_by('genotype').agg([
                pl.mean('volume_per_fish').alias('mean_volume_per_fish'),
                pl.median('volume_per_fish').alias('median_volume_per_fish'),
                pl.min('volume_per_fish').alias('min_volume_per_fish'),
                pl.max('volume_per_fish').alias('max_volume_per_fish')
            ])
            summary = summary.join(volume_stats, on='genotype', how='left')

        # Add housing type stats if available
        if 'container_type' in latest_records.columns:
            container_stats = latest_records.group_by(['genotype', 'container_type']).agg([
                pl.n_unique('dish_id').alias('container_count'),
                pl.mean('survival_rate').alias('container_mean_survival')
            ])
            # Pivot so each container type becomes its own column pair
            for ct in latest_records['container_type'].unique().to_list():
                if ct is None:
                    continue
                ct_data = container_stats.filter(pl.col('container_type') == ct)
                if ct_data.height > 0:
                    ct_renamed = ct_data.select([
                        'genotype',
                        pl.col('container_count').alias(f'{ct}_count'),
                        pl.col('container_mean_survival').alias(f'{ct}_mean_survival'),
                    ])
                    summary = summary.join(ct_renamed, on='genotype', how='left')

        logger.info(f"Created summary with {summary.height} rows")
        return summary
    except Exception as e:
        logger.error(f"Error creating summary: {e}", exc_info=True)
        # Return empty DataFrame on error
        return pl.DataFrame({
             'genotype': [], 'count': [], 'mean_survival': [], 'median_survival': [],
             'min_survival': [], 'max_survival': [], 'std_survival': []
         }, schema={
             'genotype': pl.Utf8, 'count': pl.UInt32, 'mean_survival': pl.Float64,
             'median_survival': pl.Float64, 'min_survival': pl.Float64,
             'max_survival': pl.Float64, 'std_survival': pl.Float64
         })

