import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import InlineTextLink from './InlineTextLink.tsx'
import InlineTextLinkWithArrow from './InlineTextLinkWithArrow.tsx'
import Footer from './Footer.tsx'


        type FooterColumnData = {
            heading: string;
            headingId: string;
            links: string[];
            arrowLabel?: string;
        }
    
// Component

function FooterColumn({
  dataId
}: {
  dataId: string;
}) {
  const {
    heading,
    headingId,
    links,
    arrowLabel
  }: FooterColumnData = getFooterColumnData(dataId);

  return (
    <ul role={"list"} className={"footerColumn_list__xEsxo"}>
      <li role={"none"} id={headingId}>
        <p className={"text_text__cG3pf text_textWeightSemibold___lCV0 text_textSizeNav__T2a_b"}>
          {heading}
        </p>
      </li>
      {links.map((label) => (
        <FooterColumnLinkItem key={label} label={label} />
      ))}
      {arrowLabel && (
        <FooterColumnArrowItem label={arrowLabel} />
      )}
    </ul>
  );
}
    

// Subcomponents

function FooterColumnLinkItem({ label }: { label: string }) {
  return (
    <li className={"footerColumnItem_footerColumnItem__WBiQ9"}>
      <InlineTextLink label={label} />
    </li>
  );
}

function FooterColumnArrowItem({ label }: { label: string }) {
  return (
    <li
      className={"typography_typography__Exx2D"}
      style={{
        marginTop: "auto",
        "--typography-font": "var(--typography-sans-150-bold-font)",
        "--typography-font-sm": "var(--typography-sans-150-bold-font)",
        "--typography-letter-spacing": "var(--typography-sans-150-bold-letter-spacing)",
        "--typography-letter-spacing-sm": "var(--typography-sans-150-bold-letter-spacing)",
        "--typography-color": "var(--color-black)"
      } as React.CSSProperties}
    >
      <InlineTextLinkWithArrow label={label} />
    </li>
  );
}
    


function getFooterColumnData(id: string): FooterColumnData {
  const key = String(id);

  const data: Record<string, FooterColumnData> = {
    "0": {
      heading: "Company",
      headingId: ":rb:",
      links: [
        "About us",
        "Careers",
        "Security",
        "Status",
        "Terms & privacy",
        "Your privacy rights"
      ]
    },
    "1": {
      heading: "Download",
      headingId: ":rc:",
      links: [
        "iOS & Android",
        "Mac & Windows",
        "Mail",
        "Calendar",
        "Web Clipper"
      ]
    },
    "2": {
      heading: "Resources",
      headingId: ":rd:",
      links: [
        "Help center",
        "Pricing",
        "Blog",
        "Community",
        "Integrations",
        "Templates",
        "Partner programs"
      ]
    },
    "3": {
      heading: "Notion for",
      headingId: ":re:",
      links: [
        "Enterprise",
        "Small business",
        "Personal"
      ],
      arrowLabel: "Explore more"
    }
  };

  return data[key] ?? {
    heading: "",
    headingId: "",
    links: []
  };
}
    

export default FooterColumn
