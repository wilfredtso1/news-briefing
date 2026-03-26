import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import Solid_five_point_star from './icons/Solid_five_point_star.tsx'
import UserBaseInfo from './UserBaseInfo.tsx'


        type ReviewItemData = {
            wrapperClassName: string;
            title: string;
            body: string;
            avatarColorClass: string;
            avatarLetter: string;
            userDataId: string;
        }
    
// Component

        function ReviewItem({
            dataId
        }: {
            dataId: string;
        }) {
            const {
                wrapperClassName,
                title,
                body,
                avatarColorClass,
                avatarLetter,
                userDataId
            }: ReviewItemData = getReviewItemData(dataId);

            return (
                <div role={"listitem"} className={wrapperClassName}>
                    <div className={"TemplateReviews_reviewContent__PvL29"}>
                        <div className={"TemplateReviews_reviewHeader__6GLQ3"}>
                            <span
                                className={"typography_typography__Exx2D"}
                                style={{
                                    "--typography-font": "var(--typography-sans-150-semibold-font)",
                                    "--typography-font-sm": "var(--typography-sans-150-semibold-font)",
                                    "--typography-letter-spacing": "var(--typography-sans-150-semibold-letter-spacing)",
                                    "--typography-letter-spacing-sm": "var(--typography-sans-150-semibold-letter-spacing)",
                                    "--typography-color": "inherit"
                                } as React.CSSProperties}
                            >
                                {title}
                            </span>
                            <div className={"TemplateRatings_stars__FlIIN"} role={"presentation"}>
                                <Stars />
                            </div>
                        </div>
                        <span
                            className={"typography_typography__Exx2D"}
                            style={{
                                "--typography-font": "var(--typography-sans-100-regular-font)",
                                "--typography-font-sm": "var(--typography-sans-100-regular-font)",
                                "--typography-letter-spacing": "var(--typography-sans-100-regular-letter-spacing)",
                                "--typography-letter-spacing-sm": "var(--typography-sans-100-regular-letter-spacing)",
                                "--typography-color": "inherit"
                            } as React.CSSProperties}
                        >
                            {body}
                        </span>
                        <div className={"UserBaseInfo_container__72ryf"}>
                            <div className={"UserBaseInfo_userInfoContainer__UAQc_"}>
                                <span
                                    className={`avatar_avatar__FDZwN ${avatarColorClass} avatar_sizeXs__W125u`}
                                    style={{ "--avatar-size": "20px" } as React.CSSProperties}
                                >
                                    <span>
                                        {avatarLetter}
                                    </span>
                                </span>

                                <UserBaseInfo dataId={userDataId} />
                            </div>
                        </div>
                    </div>
                </div>
            );
        }
    

// Subcomponents

        function Stars() {
            return (
                <>
                    <span className={"TemplateRatings_filled__diZfz"}>
                        <Solid_five_point_star />
                    </span>
                    <span className={"TemplateRatings_filled__diZfz"}>
                        <Solid_five_point_star />
                    </span>
                    <span className={"TemplateRatings_filled__diZfz"}>
                        <Solid_five_point_star />
                    </span>
                    <span className={"TemplateRatings_filled__diZfz"}>
                        <Solid_five_point_star />
                    </span>
                    <span className={"TemplateRatings_filled__diZfz"}>
                        <Solid_five_point_star />
                    </span>
                </>
            );
        }
    


        function getReviewItemData(id: string): ReviewItemData {
            const key = String(id);
            const map: Record<string, ReviewItemData> = {
                "0": {
                    wrapperClassName: "TemplateReviews_review__PXgZ4",
                    title: "Very useful template",
                    body: "It's easy to use, I didn't know you can make forms in Notion",
                    avatarColorClass: "avatar_colorYellow__LvUEY",
                    avatarLetter: "S",
                    userDataId: "1"
                },
                "1": {
                    wrapperClassName: "TemplateReviews_review__PXgZ4",
                    title: "Great",
                    body: "Good stuff i love how simple it is and easy to use",
                    avatarColorClass: "avatar_colorBlue__VSUKs",
                    avatarLetter: "J",
                    userDataId: "2"
                },
                "2": {
                    wrapperClassName: "TemplateReviews_review__PXgZ4 TemplateReviews_lastReview__R20LW",
                    title: "Easy to use",
                    body: "Great, lite form to use to gather simple inquiries and have it archived in a table on the same page!",
                    avatarColorClass: "avatar_colorRed__7WBVt",
                    avatarLetter: "C",
                    userDataId: "3"
                }
            };

            return map[key] || map["0"];
        }
    

export default ReviewItem
