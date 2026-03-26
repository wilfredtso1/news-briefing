import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import RichTextArticle from './RichTextArticle.tsx'
import TemplateDetailLinks from './TemplateDetailLinks.tsx'
import MarketplaceCategories from './MarketplaceCategories.tsx'
import SocialShareList from './SocialShareList.tsx'


// Component

        function TemplateDescription({
            description,
            lastUpdatedLabel
        }: {
            description: string;
            lastUpdatedLabel: string;
        }) {
            return (
                <section className={"template_templateDescriptionTest__WHtHM"}>
                    <div className={"template_readMoreContainer__4ekEN"}>
                        <div className={"template_readMoreContent__3Bq_C"} style={{ maxHeight: "initial" }}>
                            <header>
                                <div className={"Spacer_spacer__Hz1_q"} style={{ minHeight: "16px" }}>
                                </div>
                                <h5
                                    className={"typography_typography__Exx2D heading_heading__OmVf6"}
                                    style={{
                                        "--typography-font": "var(--typography-sans-300-bold-font)",
                                        "--typography-font-sm": "var(--typography-sans-300-bold-font)",
                                        "--typography-letter-spacing": "var(--typography-sans-300-bold-letter-spacing)",
                                        "--typography-letter-spacing-sm": "var(--typography-sans-300-bold-letter-spacing)",
                                        "--typography-color": "inherit"
                                    } as React.CSSProperties}
                                >
                                    About this template
                                </h5>
                                <div className={"Spacer_spacer__Hz1_q"} style={{ minHeight: "16px" }}>
                                </div>
                                <RichTextArticle text={description} />
                            </header>
                        </div>
                    </div>
                    <section>
                        <h6
                            className={"typography_typography__Exx2D heading_heading__OmVf6"}
                            style={{
                                "--typography-font": "var(--typography-sans-50-medium-font)",
                                "--typography-font-sm": "var(--typography-sans-50-medium-font)",
                                "--typography-letter-spacing": "var(--typography-sans-50-medium-letter-spacing)",
                                "--typography-letter-spacing-sm": "var(--typography-sans-50-medium-letter-spacing)",
                                "--typography-color": "var(--color-gray-400)"
                            } as React.CSSProperties}
                        >
                            Categories
                        </h6>
                        <MarketplaceCategories />
                    </section>
                    <section>
                        <h6
                            className={"typography_typography__Exx2D heading_heading__OmVf6"}
                            style={{
                                "--typography-font": "var(--typography-sans-50-medium-font)",
                                "--typography-font-sm": "var(--typography-sans-50-medium-font)",
                                "--typography-letter-spacing": "var(--typography-sans-50-medium-letter-spacing)",
                                "--typography-letter-spacing-sm": "var(--typography-sans-50-medium-letter-spacing)",
                                "--typography-color": "var(--color-gray-400)"
                            } as React.CSSProperties}
                        >
                            About this creator
                        </h6>
                        <TemplateDetailLinks />
                    </section>
                    <footer className={"templateDetail_footer__HCzBK"}>
                        <h6
                            className={"typography_typography__Exx2D heading_heading__OmVf6"}
                            style={{
                                "--typography-font": "var(--typography-sans-50-medium-font)",
                                "--typography-font-sm": "var(--typography-sans-50-medium-font)",
                                "--typography-letter-spacing": "var(--typography-sans-50-medium-letter-spacing)",
                                "--typography-letter-spacing-sm": "var(--typography-sans-50-medium-letter-spacing)",
                                "--typography-color": "var(--color-gray-400)"
                            } as React.CSSProperties}
                        >
                            Share this template
                        </h6>
                        <div className={"socialShare_share__JZdeS"}>
                            <SocialShareList />
                        </div>
                        <span
                            className={"typography_typography__Exx2D"}
                            style={{
                                "--typography-font": "var(--typography-sans-50-regular-font)",
                                "--typography-font-sm": "var(--typography-sans-50-regular-font)",
                                "--typography-letter-spacing": "var(--typography-sans-50-regular-letter-spacing)",
                                "--typography-letter-spacing-sm": "var(--typography-sans-50-regular-letter-spacing)",
                                "--typography-color": "inherit"
                            } as React.CSSProperties}
                        >
                            {lastUpdatedLabel}
                        </span>
                        <p
                            className={"typography_typography__Exx2D templateDetail_termsLink__L2yVQ"}
                            style={{
                                "--typography-font": "var(--typography-sans-50-medium-font)",
                                "--typography-font-sm": "var(--typography-sans-50-medium-font)",
                                "--typography-letter-spacing": "var(--typography-sans-50-medium-letter-spacing)",
                                "--typography-letter-spacing-sm": "var(--typography-sans-50-medium-letter-spacing)",
                                "--typography-color": "inherit"
                            } as React.CSSProperties}
                        >
                            <a>
                                Terms and Conditions
                            </a>
                        </p>
                    </footer>
                </section>
            );
        }
    

export default TemplateDescription
