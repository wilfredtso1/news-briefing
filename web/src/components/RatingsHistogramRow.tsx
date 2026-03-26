import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import Solid_five_point_star from './icons/Solid_five_point_star.tsx'
import Star_outline from './icons/Star_outline.tsx'


    
// Component

function RatingsHistogramRow({
  rating,
  percentageLabel,
  fillWidth
}: {
  rating: number;
  percentageLabel: string;
  fillWidth: string;
}) {
  return (
    <div className={"TemplateRatings_histogramRow__0wblr"} role={"img"}>
      <div className={"TemplateRatings_stars__FlIIN"} role={"presentation"}>
        <Stars rating={rating} />
      </div>
      <div className={"oldTooltip_tooltipTarget__aovlU oldTooltip_fillSpace__glY_P"}>
        <div
          className={"oldTooltip_tooltip__Thq7W"}
          style={{ "--tooltip-width": "48px", top: "auto", insetInlineStart: "auto", visibility: "hidden" } as React.CSSProperties}
        >
          <div className={"oldTooltip_tooltipText__k59No"}>
            <p className={"text_text__cG3pf text_textWeightMedium__qgxjp text_textColorWhite__H70dC text_textSizeFootnote__gdfM_ text_textWithMargin__xS5ac"}>
              {percentageLabel}
            </p>
          </div>
        </div>
        <div className={"TemplateRatings_barContainer__uin93"}>
          <div className={"TemplateRatings_bar__AT9IL"}>
            <div
              className={"TemplateRatings_fill__qDA3D"}
              style={{ width: fillWidth }}
            >
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
    

// Subcomponents

function Stars({ rating }: { rating: number }) {
  return (
    <>
      {Array.from({ length: 5 }).map((_, index) => {
        const isFilled = index < rating;
        return isFilled ? (
          <span
            key={index}
            className={"TemplateRatings_filled__diZfz"}
          >
            <Solid_five_point_star />
          </span>
        ) : (
          <span
            key={index}
            className={"TemplateRatings_unfilled__hLa4Y"}
          >
            <Star_outline />
          </span>
        );
      })}
    </>
  );
}
    

export default RatingsHistogramRow
