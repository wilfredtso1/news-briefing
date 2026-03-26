import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import TemplateGalleryLink from './TemplateGalleryLink.tsx'
import TemplateCard from './TemplateCard.tsx'


        type TemplateGalleryRowData = {
            headingId: string;
            headingText: string;
            showLink: boolean;
            cards: JSX.Element[];
        }
    
// Component

        function TemplateGalleryRow({
            dataId
        }: {
            dataId: string;
        }) {
            const {
                headingId,
                headingText,
                showLink,
                cards
            }: TemplateGalleryRowData = getTemplateGalleryRowData(dataId);

            return (
                <section className={"TemplateGalleryContentRow_contentRow__63ESj"}>
                    <div className={"TemplateGalleryContentRow_header__F3cCg"}>
                        <div className={"TemplateGalleryContentRow_heading__ofqyJ"}>
                            <h3
                                id={headingId}
                                className={"typography_typography__Exx2D heading_heading__OmVf6"}
                                style={{
                                    "--typography-font": "var(--typography-sans-400-bold-font)",
                                    "--typography-font-sm": "var(--typography-sans-500-bold-font)",
                                    "--typography-letter-spacing": "var(--typography-sans-400-bold-letter-spacing)",
                                    "--typography-letter-spacing-sm": "var(--typography-sans-500-bold-letter-spacing)",
                                    "--typography-color": "inherit"
                                } as React.CSSProperties}
                            >
                                {headingText}
                            </h3>
                        </div>
                        {showLink ? <TemplateGalleryLink /> : null}
                    </div>
                    <div className={"grid_grid__caono"}>
                        {cards.map((card, index) => (
                            <GridItem key={index}>
                                {card}
                            </GridItem>
                        ))}
                    </div>
                </section>
            );
        }
    

// Subcomponents

        function GridItem({ children }: { children: React.ReactNode }) {
            return (
                <div className={"gridItem_gridItem__aOo8I gridItem_span4__4hMOE"}>
                    {children}
                </div>
            );
        }
    


        function getTemplateGalleryRowData(id: string): TemplateGalleryRowData {
            const key = String(id);

            if (key === "0") {
                return {
                    headingId: ":r6:",
                    headingText: "More by Notion",
                    showLink: true,
                    cards: [
                        <TemplateCard imgId="4" userDataId="4" />,
                        <TemplateCard imgId="5" userDataId="5" />,
                        <TemplateCard imgId="6" userDataId="6" />
                    ]
                };
            }

            if (key === "1") {
                return {
                    headingId: ":r7:",
                    headingText: "More like this",
                    showLink: false,
                    cards: [
                        <TemplateCard
                            imgId="7"
                            useCustomUserInfo={true}
                            imageLinkId="8"
                            title="Website Contact Form"
                            creatorName="Forms"
                        />,
                        <TemplateCard
                            imgId="9"
                            useCustomUserInfo={true}
                            imageLinkId="10"
                            title="Contact Form Plugin"
                            creatorName="Stack Seekers"
                        />,
                        <TemplateCard
                            imgId="11"
                            useCustomUserInfo={true}
                            imageLinkId="12"
                            title="Client Contact Form"
                            creatorName="Akshay Raveendran"
                        />
                    ]
                };
            }

            return {
                headingId: "",
                headingText: "",
                showLink: false,
                cards: []
            };
        }
    

export default TemplateGalleryRow
