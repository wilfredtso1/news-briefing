import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import Diagonal_gray_slash from './icons/Diagonal_gray_slash.tsx'


// Component

        function AverageRating({
            average,
            max
        }: {
            average: string | number;
            max: string | number;
        }) {
            return (
                <div className={"TemplateRatings_averageHeading__FRrtM"}>
                    <span className={"TemplateRatings_averageNumber__llvw9"}>
                        {average}
                    </span>
                    <Diagonal_gray_slash />
                    <span className={"TemplateRatings_numberFive__20FKC"}>
                        {max}
                    </span>
                </div>
            );
        }
    

export default AverageRating
